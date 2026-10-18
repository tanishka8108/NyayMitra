"""Lawyer registration + access rules — the Phase 2 checks.

Run from the API folder::

    python -m pytest

Hermetic like ``test_auth_api.py``: every test gets its own
throwaway SQLite file via ``tmp_path`` (``NYAYMITRA_AUTH_DB``).

Covered, in the order the brief lists it:

1.  registration creates a LAWYER account + linked registration,
    signed in immediately, PENDING by default
2.  licence / registration ID required and stored, unique
3.  practice areas required, cleaned, stored
4.  PENDING is server-assigned — the client cannot send a status
    (nor a role) and cannot self-approve at the door
5.  password rules reuse the same validators as user registration
6.  lawyer login is the SAME endpoint and rules as user login
7.  /me and /lawyer/profile expose the status, never a hash
8.  require_verified_lawyer: PENDING / APPROVED / REJECTED each
    answer as specified, and non-lawyers are refused
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from auth import security
from database.sqlite_db import connect

GOOD_PASSWORD = "password123"


# =========================================================
# FIXTURES
# =========================================================


@pytest.fixture(scope="session")
def app():
    from main import app as application

    return application


@pytest.fixture()
def auth_db(tmp_path, monkeypatch):
    """A private SQLite file for this test — the dev DB stays clean."""
    path = tmp_path / "auth.db"
    monkeypatch.setenv("NYAYMITRA_AUTH_DB", str(path))
    return path


@pytest.fixture()
def client(app, auth_db):
    return TestClient(app, raise_server_exceptions=False)


def register_lawyer(
    client,
    email: str = "advocate@example.com",
    password: str = GOOD_PASSWORD,
    **overrides,
):
    payload = {
        "full_name": "Test Advocate",
        "email": email,
        "password": password,
        "password_confirmation": password,
        "license_id": "ENR/2024/0001",
        "practice_areas": ["Criminal Law", "Family Law"],
    }
    payload.update(overrides)
    return client.post("/api/auth/register/lawyer", json=payload)


def register_user(client, email: str = "citizen@example.com"):
    return client.post(
        "/api/auth/register",
        json={
            "full_name": "Test Citizen",
            "email": email,
            "password": GOOD_PASSWORD,
            "password_confirmation": GOOD_PASSWORD,
        },
    )


def lawyer_row(auth_db, email: str = "advocate@example.com"):
    connection = sqlite3.connect(str(auth_db))
    connection.row_factory = sqlite3.Row
    try:
        return connection.execute(
            """
            SELECT l.*, u.role, u.email AS account_email,
                   u.password_hash
            FROM lawyers l
            JOIN users u ON u.id = l.user_id
            WHERE u.email = ?
            """,
            (email,),
        ).fetchone()
    finally:
        connection.close()


def count_rows(auth_db, table: str) -> int:
    # Via sqlite_db.connect so the schema exists even when the
    # request was rejected before any handler ever opened the file.
    connection = connect()
    try:
        return connection.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()[0]
    finally:
        connection.close()


def all_db_bytes(auth_db) -> bytes:
    chunks = []
    for path in sorted(Path(auth_db).parent.iterdir()):
        if path.is_file():
            chunks.append(path.read_bytes())
    return b"".join(chunks)


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# =========================================================
# 1 — REGISTRATION: PENDING by default
# =========================================================


def test_lawyer_registration_lands_pending_and_signed_in(
    client, auth_db
):
    response = register_lawyer(client)

    assert response.status_code == 201

    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]

    user = body["user"]
    assert user["role"] == "LAWYER"
    assert user["lawyer_id"] == "LAWYER_0001"
    assert user["verification_status"] == "PENDING"
    assert user["is_demo"] is False
    assert user["email"] == "advocate@example.com"

    # No hash, no plaintext, no password field in the response.
    assert "pbkdf2" not in response.text
    assert GOOD_PASSWORD not in response.text
    assert "password_hash" not in response.text

    row = lawyer_row(auth_db)
    assert row is not None
    assert row["role"] == "LAWYER"
    assert row["verification_status"] == "PENDING"
    assert row["license_id"] == "ENR/2024/0001"
    assert row["practice_areas"] == "Criminal Law; Family Law"
    assert row["verified_by"] is None
    assert row["verified_at"] is None

    # Password stored only as a PBKDF2 hash.
    assert row["password_hash"].startswith(
        f"pbkdf2_sha256${security.PBKDF2_ITERATIONS}$"
    )
    assert GOOD_PASSWORD.encode() not in all_db_bytes(auth_db)


def test_lawyer_ids_increment_and_stay_unique(client, auth_db):
    first = register_lawyer(
        client, email="one@example.com", license_id="ENR/2024/0001"
    )
    second = register_lawyer(
        client, email="two@example.com", license_id="ENR/2024/0002"
    )

    assert first.status_code == 201
    assert second.status_code == 201

    assert first.json()["user"]["lawyer_id"] == "LAWYER_0001"
    assert second.json()["user"]["lawyer_id"] == "LAWYER_0002"


# =========================================================
# 2-3 — LICENCE AND PRACTICE AREAS
# =========================================================


def test_duplicate_email_is_rejected(client, auth_db):
    assert register_user(client, email="advocate@example.com").status_code == 201

    response = register_lawyer(client)

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "An account with this email already exists."
    )
    # No orphaned lawyer row behind the failed registration.
    assert count_rows(auth_db, "lawyers") == 0


def test_duplicate_licence_is_rejected_without_orphan_account(
    client, auth_db
):
    assert register_lawyer(client, email="first@example.com").status_code == 201

    response = register_lawyer(client, email="second@example.com")

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "An account with this licence number already exists."
    )

    # The users row the transaction had written is rolled back too.
    assert count_rows(auth_db, "users") == 1
    assert count_rows(auth_db, "lawyers") == 1


def test_practice_areas_are_deduplicated_and_trimmed(client):
    response = register_lawyer(
        client,
        practice_areas=[
            "  Criminal Law ",
            "criminal law",
            "Constitutional Law",
        ],
    )

    assert response.status_code == 201

    # Read back through the profile endpoint as a clean array:
    # trimmed, case-insensitively de-duplicated, order preserved.
    profile = client.get(
        "/api/auth/lawyer/profile",
        headers=auth_header(response.json()["access_token"]),
    ).json()

    assert profile["practice_areas"] == [
        "Criminal Law",
        "Constitutional Law",
    ]


@pytest.mark.parametrize(
    ("overrides", "expected_detail"),
    [
        ({"license_id": "   "}, "Enter your licence or registration number."),
        ({"license_id": "x" * 101},
         "Licence number must be 100 characters or fewer."),
        ({"practice_areas": []}, "List at least one practice area."),
        ({"practice_areas": ["Criminal Law", "  "]},
         "Practice areas cannot be blank."),
        ({"practice_areas": ["Criminal Law"] * 11},
         "List at most 10 practice areas."),
        ({"practice_areas": ["x" * 101]},
         "Each practice area must be 100 characters or fewer."),
        ({"password_confirmation": "other12345"},
         "Passwords do not match."),
        ({"password": "short", "password_confirmation": "short"},
         "Password must be at least 8 characters."),
        ({"email": "not-an-email"}, "Enter a valid email address."),
        ({"full_name": "   "}, "Enter your full name."),
    ],
)
def test_registration_validation(client, overrides, expected_detail):
    response = register_lawyer(client, **overrides)

    assert response.status_code == 400
    assert response.json()["detail"] == expected_detail


def test_missing_licence_or_areas_is_422(client):
    no_license = client.post(
        "/api/auth/register/lawyer",
        json={
            "full_name": "No Licence",
            "email": "nl@example.com",
            "password": GOOD_PASSWORD,
            "password_confirmation": GOOD_PASSWORD,
            "practice_areas": ["Criminal Law"],
        },
    )
    assert no_license.status_code == 422

    no_areas = client.post(
        "/api/auth/register/lawyer",
        json={
            "full_name": "No Areas",
            "email": "na@example.com",
            "password": GOOD_PASSWORD,
            "password_confirmation": GOOD_PASSWORD,
            "license_id": "ENR/2024/0002",
        },
    )
    assert no_areas.status_code == 422


# =========================================================
# 4 — THE CLIENT CANNOT CHOOSE ITS STATUS OR ROLE
# =========================================================


@pytest.mark.parametrize(
    "smuggled",
    [
        {"verification_status": "APPROVED"},
        {"verification_status": "REJECTED"},
        {"verified_by": 1},
        {"role": "ADMIN"},
        {"role": "LAWYER"},
        {"lawyer_id": "LAWYER_0003"},
    ],
)
def test_client_cannot_smuggle_a_status_role_or_id(
    client, auth_db, smuggled
):
    """The self-approval attempt at the door: any extra field the
    model does not know — chief among them ``verification_status``
    — is a 422, not a quietly ignored key."""
    response = register_lawyer(client, **smuggled)

    assert response.status_code == 422

    # Nothing was created at all.
    assert count_rows(auth_db, "users") == 0
    assert count_rows(auth_db, "lawyers") == 0


# =========================================================
# 6 — LOGIN IS THE SAME SYSTEM FOR LAWYERS
# =========================================================


def test_lawyer_logs_in_through_the_same_endpoint(client):
    assert register_lawyer(client).status_code == 201

    response = client.post(
        "/api/auth/login",
        json={
            "email": "  ADVOCATE@example.com ",
            "password": GOOD_PASSWORD,
        },
    )

    assert response.status_code == 200

    body = response.json()
    assert body["user"]["role"] == "LAWYER"
    assert body["user"]["lawyer_id"] == "LAWYER_0001"
    assert body["user"]["verification_status"] == "PENDING"
    assert "pbkdf2" not in response.text


def test_lawyer_wrong_password_answers_like_everyone_else(client):
    assert register_lawyer(client).status_code == 201

    wrong = client.post(
        "/api/auth/login",
        json={"email": "advocate@example.com", "password": "wrong-pass-123"},
    )
    unknown = client.post(
        "/api/auth/login",
        json={"email": "nobody@example.com", "password": GOOD_PASSWORD},
    )

    assert wrong.status_code == 401
    assert unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"]


# =========================================================
# 7 — /me AND /lawyer/profile
# =========================================================


def test_me_carries_the_status_but_never_a_hash(client):
    token = register_lawyer(client).json()["access_token"]

    response = client.get("/api/auth/me", headers=auth_header(token))

    assert response.status_code == 200
    assert response.json()["verification_status"] == "PENDING"
    assert response.json()["lawyer_id"] == "LAWYER_0001"
    assert "password_hash" not in response.text
    assert "pbkdf2" not in response.text


def test_citizen_me_has_no_verification_status(client):
    token = register_user(client).json()["access_token"]

    response = client.get("/api/auth/me", headers=auth_header(token))

    assert response.status_code == 200
    assert response.json()["verification_status"] is None
    assert response.json()["lawyer_id"] is None


def test_lawyer_profile_returns_own_registration_only(client):
    token = register_lawyer(client).json()["access_token"]

    response = client.get(
        "/api/auth/lawyer/profile", headers=auth_header(token)
    )

    assert response.status_code == 200

    profile = response.json()
    assert profile["lawyer_id"] == "LAWYER_0001"
    assert profile["license_id"] == "ENR/2024/0001"
    assert profile["practice_areas"] == [
        "Criminal Law",
        "Family Law",
    ]
    assert profile["verification_status"] == "PENDING"
    assert profile["verified_at"] is None
    assert profile["email"] == "advocate@example.com"
    assert "password_hash" not in response.text
    assert "pbkdf2" not in response.text


def test_lawyer_profile_is_for_lawyers_only(client):
    lawyer_token = register_lawyer(client).json()["access_token"]
    citizen_token = register_user(client).json()["access_token"]

    assert client.get("/api/auth/lawyer/profile").status_code == 401

    citizen = client.get(
        "/api/auth/lawyer/profile",
        headers=auth_header(citizen_token),
    )
    assert citizen.status_code == 403
    assert citizen.json()["detail"] == (
        "You do not have permission to perform this action."
    )

    assert (
        client.get(
            "/api/auth/lawyer/profile",
            headers=auth_header(lawyer_token),
        ).status_code
        == 200
    )


# =========================================================
# 8 — PENDING / APPROVED / REJECTED ACCESS RULES
# =========================================================


def set_status(auth_db, status: str, email: str = "advocate@example.com"):
    """Flip the row directly — the admin API itself is exercised in
    test_verification_admin.py; this file is about the guard."""
    connection = connect()
    try:
        connection.execute(
            """
            UPDATE lawyers
            SET verification_status = ?,
                verified_by = NULL,
                verified_at = NULL
            WHERE user_id = (SELECT id FROM users WHERE email = ?)
            """,
            (status, email),
        )
        connection.commit()
    finally:
        connection.close()


@pytest.fixture()
def guarded_app():
    """A one-route app carrying the real dependency — the same
    pattern test_auth_api.py uses for require_role."""
    from fastapi import Depends, FastAPI

    guarded = FastAPI()

    @guarded.get(
        "/lawyer-feature",
        dependencies=[Depends(security.require_verified_lawyer)],
    )
    def lawyer_feature():
        return {"ok": True}

    return guarded


def test_access_rules_for_all_three_states(
    client, auth_db, guarded_app
):
    lawyer_token = register_lawyer(client).json()["access_token"]
    citizen_token = register_user(client).json()["access_token"]
    guarded_client = TestClient(guarded_app, raise_server_exceptions=False)

    # Signed out -> 401.
    assert guarded_client.get("/lawyer-feature").status_code == 401

    # PENDING -> refused with their own status, plainly worded.
    pending = guarded_client.get(
        "/lawyer-feature", headers=auth_header(lawyer_token)
    )
    assert pending.status_code == 403
    assert pending.json()["detail"] == (
        "Your lawyer registration is pending approval."
    )

    # A citizen is not a lawyer at all -> the fixed generic 403.
    citizen = guarded_client.get(
        "/lawyer-feature", headers=auth_header(citizen_token)
    )
    assert citizen.status_code == 403
    assert citizen.json()["detail"] == (
        "You do not have permission to perform this action."
    )

    # APPROVED -> through.
    set_status(auth_db, "APPROVED")
    approved = guarded_client.get(
        "/lawyer-feature", headers=auth_header(lawyer_token)
    )
    assert approved.status_code == 200
    assert approved.json() == {"ok": True}

    # The same session now reads APPROVED on /me — no re-login.
    me = client.get("/api/auth/me", headers=auth_header(lawyer_token))
    assert me.json()["verification_status"] == "APPROVED"

    # REJECTED -> refused with the rejection wording.
    set_status(auth_db, "REJECTED")
    rejected = guarded_client.get(
        "/lawyer-feature", headers=auth_header(lawyer_token)
    )
    assert rejected.status_code == 403
    assert rejected.json()["detail"] == (
        "Your lawyer registration has been rejected."
    )

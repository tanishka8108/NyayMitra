"""Authentication API — the checks the feature is judged by.

Run from the API folder::

    python -m pytest

Hermetic: every test gets its own throwaway SQLite file via ``tmp_path``
(``NYAYMITRA_AUTH_DB``), so nothing here ever touches the development
database, and the demo accounts are seeded only in ``test_auth_seed.py``
— never as a side effect of these tests.

Covered, in the order the brief lists it:

1.  registration returns a session and a safe user object
2.  duplicate email rejected (409)
3.  the client cannot choose a role (extra ``role`` field -> 422,
    database role is USER)
4.  validation: mismatch / short / bad email / empty name -> 400
5.  passwords stored only as PBKDF2 hashes, unique salt per user
6.  login success, wrong password, unknown email (identical 401)
7.  GET /api/auth/me works with the token (protected route)
8.  /me without or with a garbage token -> 401
9.  logout invalidates the token
10. session mechanics: server-side row with a future expiry
11. require_role(): 401 signed out, 403 wrong role, 200 right role
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


def register_user(
    client,
    email: str = "citizen@example.com",
    password: str = GOOD_PASSWORD,
    **overrides,
):
    payload = {
        "full_name": "Test Citizen",
        "email": email,
        "password": password,
        "password_confirmation": password,
    }
    payload.update(overrides)
    return client.post("/api/auth/register", json=payload)


def all_db_bytes(auth_db) -> bytes:
    """Raw bytes of the DB and its WAL sidecars.

    Reads everything so an assertion about stored bytes cannot be
    fooled by pages still living in the write-ahead log.
    """
    chunks = []
    for path in sorted(Path(auth_db).parent.iterdir()):
        if path.is_file():
            chunks.append(path.read_bytes())
    return b"".join(chunks)


def make_user(email: str, role: str) -> int:
    """Insert a user directly (for guard tests) and return its id."""
    connection = connect()
    try:
        cursor = connection.execute(
            """
            INSERT INTO users (name, email, password_hash, role, is_demo)
            VALUES (?, ?, ?, ?, 0)
            """,
            (
                f"{role} account",
                email,
                security.hash_password(GOOD_PASSWORD),
                role,
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)
    finally:
        connection.close()


# =========================================================
# 1-4 — REGISTRATION
# =========================================================


def test_register_returns_session_and_safe_user(client):
    response = register_user(client)

    assert response.status_code == 201

    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"]["user_id"] >= 1
    assert body["user"]["full_name"] == "Test Citizen"
    assert body["user"]["email"] == "citizen@example.com"
    assert body["user"]["role"] == "USER"
    assert body["user"]["lawyer_id"] is None

    # No hash, no password, no plaintext anywhere in the response.
    text = response.text
    assert "pbkdf2" not in text
    assert GOOD_PASSWORD not in text
    assert "password_hash" not in text


def test_register_rejects_duplicate_email(client):
    first = register_user(client)
    assert first.status_code == 201

    second = register_user(client)
    assert second.status_code == 409
    assert second.json()["detail"] == (
        "An account with this email already exists."
    )


def test_client_cannot_choose_a_role(client, auth_db):
    """A ``role`` field in the payload is rejected outright (422),
    and an ordinary registration always lands as USER."""
    injected = register_user(client, role="ADMIN")

    assert injected.status_code == 422

    clean = register_user(client)
    assert clean.status_code == 201
    assert clean.json()["user"]["role"] == "USER"

    connection = sqlite3.connect(str(auth_db))
    try:
        row = connection.execute(
            "SELECT role FROM users WHERE email = ?",
            ("citizen@example.com",),
        ).fetchone()
    finally:
        connection.close()

    assert row is not None
    assert row[0] == "USER"


@pytest.mark.parametrize(
    ("overrides", "expected_detail"),
    [
        ({"password_confirmation": "other12345"}, "Passwords do not match."),
        ({"password": "short", "password_confirmation": "short"},
         "Password must be at least 8 characters."),
        ({"email": "not-an-email"}, "Enter a valid email address."),
        ({"full_name": "   "}, "Enter your full name."),
    ],
)
def test_register_validation(client, overrides, expected_detail):
    response = register_user(client, **overrides)

    assert response.status_code == 400
    assert response.json()["detail"] == expected_detail


def test_register_missing_field_is_rejected(client):
    response = client.post(
        "/api/auth/register",
        json={"full_name": "No Password", "email": "np@example.com"},
    )

    assert response.status_code == 422


# =========================================================
# 5 — PASSWORD STORAGE
# =========================================================


def test_passwords_are_pbkdf2_hashed_with_unique_salts(
    client, auth_db
):
    """Same password, different hashes; PBKDF2 format; the plaintext
    appears nowhere in the stored bytes."""
    first = register_user(client, email="one@example.com")
    second = register_user(client, email="two@example.com")
    assert first.status_code == 201
    assert second.status_code == 201

    connection = sqlite3.connect(str(auth_db))
    try:
        rows = connection.execute(
            "SELECT email, password_hash FROM users ORDER BY email"
        ).fetchall()
    finally:
        connection.close()

    assert len(rows) == 2
    hashes = {row[0]: row[1] for row in rows}

    expected_prefix = (
        f"pbkdf2_sha256${security.PBKDF2_ITERATIONS}$"
    )
    for stored in hashes.values():
        assert stored.startswith(expected_prefix)

    # Unique salt => identical passwords never share a hash.
    assert hashes["one@example.com"] != hashes["two@example.com"]

    raw = all_db_bytes(auth_db)
    assert GOOD_PASSWORD.encode() not in raw
    assert b"pbkdf2" in raw  # ...but the hash itself is there.


# =========================================================
# 6 — LOGIN
# =========================================================


def test_login_success_returns_token(client):
    assert register_user(client).status_code == 201

    response = client.post(
        "/api/auth/login",
        json={"email": "citizen@example.com", "password": GOOD_PASSWORD},
    )

    assert response.status_code == 200

    body = response.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == "citizen@example.com"
    assert body["user"]["role"] == "USER"
    assert "pbkdf2" not in response.text


def test_login_is_case_insensitive_on_email(client):
    assert register_user(client).status_code == 201

    response = client.post(
        "/api/auth/login",
        json={"email": "  CITIZEN@Example.COM ", "password": GOOD_PASSWORD},
    )

    assert response.status_code == 200


def test_wrong_password_and_unknown_email_answer_identically(client):
    assert register_user(client).status_code == 201

    wrong_password = client.post(
        "/api/auth/login",
        json={"email": "citizen@example.com", "password": "wrong-pass-123"},
    )
    unknown_email = client.post(
        "/api/auth/login",
        json={"email": "nobody@example.com", "password": GOOD_PASSWORD},
    )

    assert wrong_password.status_code == 401
    assert unknown_email.status_code == 401
    # Identical message: accounts cannot be enumerated.
    assert wrong_password.json()["detail"] == (
        unknown_email.json()["detail"]
    )
    assert wrong_password.json()["detail"] == (
        "Invalid email or password."
    )


# =========================================================
# 7-10 — PROTECTED ROUTE, SESSION, LOGOUT
# =========================================================


def test_me_requires_a_valid_token(client):
    assert client.get("/api/auth/me").status_code == 401
    assert (
        client.get(
            "/api/auth/me",
            headers={"Authorization": "Token abc123"},
        ).status_code
        == 401
    )
    assert (
        client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer not-a-real-token"},
        ).status_code
        == 401
    )


def test_me_returns_the_signed_in_profile(client):
    registration = register_user(client)
    token = registration.json()["access_token"]

    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200

    user = response.json()
    assert user["email"] == "citizen@example.com"
    assert user["role"] == "USER"
    assert user["is_demo"] is False
    assert "password" not in user
    assert "password_hash" not in user
    assert "pbkdf2" not in response.text


def test_session_row_is_server_side_with_future_expiry(client, auth_db):
    token = register_user(client).json()["access_token"]

    connection = sqlite3.connect(str(auth_db))
    try:
        rows = connection.execute(
            "SELECT token_hash, user_id, expires_at FROM sessions"
        ).fetchall()
    finally:
        connection.close()

    assert len(rows) == 1
    token_hash, user_id, expires_at = rows[0]

    # The raw token is nowhere in the table — only its SHA-256.
    assert token.encode() not in all_db_bytes(auth_db)
    import hashlib

    assert token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert user_id >= 1

    from datetime import datetime, timezone

    expires = datetime.fromisoformat(expires_at)
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    assert expires > datetime.now(timezone.utc)


def test_logout_invalidates_the_token(client):
    token = register_user(client).json()["access_token"]
    auth = {"Authorization": f"Bearer {token}"}

    assert client.get("/api/auth/me", headers=auth).status_code == 200

    logout = client.post("/api/auth/logout", headers=auth)
    assert logout.status_code == 200
    assert logout.json()["message"] == "Signed out."

    assert client.get("/api/auth/me", headers=auth).status_code == 401


def test_logout_still_requires_a_header(client):
    assert client.post("/api/auth/logout").status_code == 401


# =========================================================
# 11 — SERVER-SIDE ROLE GUARD
# =========================================================


def test_require_role_enforces_401_403_200(auth_db):
    """A protected route answers: 401 signed out, 403 for the wrong
    role (safe message), 200 for the right role — regardless of what
    any client-side session claims."""
    from fastapi import Depends, FastAPI

    guarded = FastAPI()

    @guarded.get(
        "/admin-only",
        dependencies=[Depends(security.require_role("ADMIN"))],
    )
    def admin_only():
        return {"ok": True}

    citizen_id = make_user("guard-citizen@example.com", "USER")
    admin_id = make_user("guard-admin@example.com", "ADMIN")

    citizen_token = security.create_session(citizen_id)
    admin_token = security.create_session(admin_id)

    guarded_client = TestClient(guarded, raise_server_exceptions=False)

    assert guarded_client.get("/admin-only").status_code == 401

    forbidden = guarded_client.get(
        "/admin-only",
        headers={"Authorization": f"Bearer {citizen_token}"},
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["detail"] == (
        "You do not have permission to perform this action."
    )

    allowed = guarded_client.get(
        "/admin-only",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert allowed.status_code == 200
    assert allowed.json() == {"ok": True}

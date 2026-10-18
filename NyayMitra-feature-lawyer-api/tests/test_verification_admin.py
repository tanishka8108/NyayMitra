"""Admin verification API — approve / reject / list, and the
server-side proof that a lawyer can never do any of it themselves.

Run from the API folder::

    python -pm pytest

Hermetic like the other auth suites: ``NYAYMITRA_AUTH_DB`` points at
a throwaway file per test.

Covered, in the order the brief lists it:

1.  ADMIN lists registrations (all / filtered), the envelope the
    Admin Dashboard renders
2.  ADMIN reads one registration in full; unknown id -> 404
3.  APPROVE / REJECT / reset to PENDING, with verified_by /
    verified_at recorded and cleared
4.  invalid status -> 422, smuggled ``verified_by`` -> 422
5.  the decision is visible to the lawyer through /me immediately
6.  self-approval protection: a lawyer token gets 403 on every
    admin route — list, detail and the PATCH for their OWN row —
    and the row stays PENDING; citizens 403, signed-out 401
7.  no response carries a password hash
"""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from auth import security
from database.sqlite_db import connect

GOOD_PASSWORD = "password123"

ADMIN_EMAIL = "admin-under-test@example.com"


# =========================================================
# FIXTURES
# =========================================================


@pytest.fixture(scope="session")
def app():
    from main import app as application

    return application


@pytest.fixture()
def auth_db(tmp_path, monkeypatch):
    path = tmp_path / "auth.db"
    monkeypatch.setenv("NYAYMITRA_AUTH_DB", str(path))
    return path


@pytest.fixture()
def client(app, auth_db):
    return TestClient(app, raise_server_exceptions=False)


def make_admin(email: str = ADMIN_EMAIL) -> int:
    """Insert an ADMIN directly and return its id.

    There is no registration path to ADMIN (by design) — the tests
    create one the same way the seeder does.
    """
    connection = connect()
    try:
        cursor = connection.execute(
            """
            INSERT INTO users (name, email, password_hash, role, is_demo)
            VALUES (?, ?, ?, 'ADMIN', 0)
            """,
            (
                "Test Admin",
                email,
                security.hash_password(GOOD_PASSWORD),
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)
    finally:
        connection.close()


@pytest.fixture()
def admin_token(auth_db) -> str:
    return security.create_session(make_admin())


def register_lawyer(
    client,
    email: str = "advocate@example.com",
    license_id: str = "ENR/2024/0001",
    **overrides,
):
    payload = {
        "full_name": "Test Advocate",
        "email": email,
        "password": GOOD_PASSWORD,
        "password_confirmation": GOOD_PASSWORD,
        "license_id": license_id,
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


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def lawyer_status(auth_db, lawyer_id: str) -> str:
    connection = sqlite3.connect(str(auth_db))
    try:
        return connection.execute(
            "SELECT verification_status FROM lawyers"
            " WHERE lawyer_id = ?",
            (lawyer_id,),
        ).fetchone()[0]
    finally:
        connection.close()


def lawyer_rule(auth_db, lawyer_id: str):
    connection = sqlite3.connect(str(auth_db))
    try:
        return connection.execute(
            "SELECT verified_by, verified_at FROM lawyers"
            " WHERE lawyer_id = ?",
            (lawyer_id,),
        ).fetchone()
    finally:
        connection.close()


# =========================================================
# 1 — LIST
# =========================================================


def test_admin_lists_registrations_with_dashboard_envelope(
    client, auth_db, admin_token
):
    first = register_lawyer(
        client, email="one@example.com", license_id="ENR/2024/0001"
    )
    second = register_lawyer(
        client, email="two@example.com", license_id="ENR/2024/0002"
    )
    assert first.status_code == 201
    assert second.status_code == 201

    response = client.get(
        "/api/admin/lawyers", headers=auth_header(admin_token)
    )

    assert response.status_code == 200

    body = response.json()
    # Same envelope GET /api/lawyers already returns, so the
    # dashboard can render both listings with one type.
    assert set(body) == {
        "count",
        "total_count",
        "page",
        "limit",
        "total_pages",
        "lawyers",
    }
    assert body["count"] == 2
    assert body["total_count"] == 2
    assert body["page"] == 1
    assert body["total_pages"] == 1

    lawyers = body["lawyers"]
    assert {entry["lawyer_id"] for entry in lawyers} == {
        "LAWYER_0001",
        "LAWYER_0002",
    }
    for entry in lawyers:
        assert entry["verification_status"] == "PENDING"
        assert entry["practice_areas"] == [
            "Criminal Law",
            "Family Law",
        ]

    # Never a hash, even on the admin path.
    assert "pbkdf2" not in response.text


def test_status_filter_selects_one_state(
    client, auth_db, admin_token
):
    register_lawyer(
        client, email="one@example.com", license_id="ENR/2024/0001"
    )
    register_lawyer(
        client, email="two@example.com", license_id="ENR/2024/0002"
    )

    # Rule on the first one through the API itself.
    approved = client.patch(
        "/api/admin/lawyers/LAWYER_0001",
        json={"verification_status": "APPROVED"},
        headers=auth_header(admin_token),
    )
    assert approved.status_code == 200

    pending = client.get(
        "/api/admin/lawyers?status=PENDING",
        headers=auth_header(admin_token),
    )
    assert pending.status_code == 200
    assert pending.json()["count"] == 1
    assert pending.json()["lawyers"][0]["lawyer_id"] == "LAWYER_0002"

    approved_list = client.get(
        "/api/admin/lawyers?status=APPROVED",
        headers=auth_header(admin_token),
    )
    assert approved_list.json()["count"] == 1
    assert approved_list.json()["lawyers"][0]["lawyer_id"] == "LAWYER_0001"


def test_unknown_status_filter_is_rejected(client, admin_token):
    response = client.get(
        "/api/admin/lawyers?status=VERIFIED",
        headers=auth_header(admin_token),
    )

    # The vocabulary is exactly PENDING / APPROVED / REJECTED.
    assert response.status_code == 422


def test_pagination_bounds(client, admin_token):
    assert (
        client.get(
            "/api/admin/lawyers?page=0",
            headers=auth_header(admin_token),
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/api/admin/lawyers?limit=1000",
            headers=auth_header(admin_token),
        ).status_code
        == 422
    )


# =========================================================
# 2 — DETAIL
# =========================================================


def test_admin_reads_one_registration_in_full(
    client, auth_db, admin_token
):
    register_lawyer(client)

    response = client.get(
        "/api/admin/lawyers/LAWYER_0001",
        headers=auth_header(admin_token),
    )

    assert response.status_code == 200

    body = response.json()
    assert body["lawyer_id"] == "LAWYER_0001"
    assert body["full_name"] == "Test Advocate"
    assert body["email"] == "advocate@example.com"
    assert body["license_id"] == "ENR/2024/0001"
    assert body["practice_areas"] == ["Criminal Law", "Family Law"]
    assert body["verification_status"] == "PENDING"
    assert body["is_demo"] is False
    assert "password_hash" not in response.text


def test_unknown_lawyer_is_404(client, admin_token):
    missing = client.get(
        "/api/admin/lawyers/LAWYER_9999",
        headers=auth_header(admin_token),
    )
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Lawyer not found"

    missing_patch = client.patch(
        "/api/admin/lawyers/LAWYER_9999",
        json={"verification_status": "APPROVED"},
        headers=auth_header(admin_token),
    )
    assert missing_patch.status_code == 404


# =========================================================
# 3-5 — THE DECISION
# =========================================================


def test_approve_records_who_ruled_and_when(client, auth_db):
    admin_id = make_admin()
    token = security.create_session(admin_id)
    register_lawyer(client)

    response = client.patch(
        "/api/admin/lawyers/LAWYER_0001",
        json={"verification_status": "APPROVED"},
        headers=auth_header(token),
    )

    assert response.status_code == 200

    body = response.json()
    assert body["verification_status"] == "APPROVED"
    assert body["verified_by"] == admin_id
    assert body["verified_at"]

    # Visible to the lawyer immediately, through the ordinary
    # protected routes — same session, no re-login.
    login = client.post(
        "/api/auth/login",
        json={
            "email": "advocate@example.com",
            "password": GOOD_PASSWORD,
        },
    )
    lawyer_token = login.json()["access_token"]

    me = client.get(
        "/api/auth/me", headers=auth_header(lawyer_token)
    )
    assert me.json()["verification_status"] == "APPROVED"

    profile = client.get(
        "/api/auth/lawyer/profile", headers=auth_header(lawyer_token)
    )
    assert profile.json()["verification_status"] == "APPROVED"
    assert profile.json()["verified_at"]


def test_reject_then_reset_clears_the_ruling(
    client, auth_db, admin_token
):
    register_lawyer(client)

    rejected = client.patch(
        "/api/admin/lawyers/LAWYER_0001",
        json={"verification_status": "REJECTED"},
        headers=auth_header(admin_token),
    )
    assert rejected.status_code == 200
    assert rejected.json()["verification_status"] == "REJECTED"
    assert rejected.json()["verified_by"] is not None
    assert rejected.json()["verified_at"]

    reset = client.patch(
        "/api/admin/lawyers/LAWYER_0001",
        json={"verification_status": "PENDING"},
        headers=auth_header(admin_token),
    )
    assert reset.status_code == 200
    assert reset.json()["verification_status"] == "PENDING"
    # "Nobody has ruled" must read that way to every screen.
    assert reset.json()["verified_by"] is None
    assert reset.json()["verified_at"] is None


def test_invalid_status_and_smuggled_fields_are_422(
    client, auth_db, admin_token
):
    register_lawyer(client)

    invalid = client.patch(
        "/api/admin/lawyers/LAWYER_0001",
        json={"verification_status": "VERIFIED"},
        headers=auth_header(admin_token),
    )
    assert invalid.status_code == 422

    smuggled = client.patch(
        "/api/admin/lawyers/LAWYER_0001",
        json={"verification_status": "APPROVED", "verified_by": 999},
        headers=auth_header(admin_token),
    )
    assert smuggled.status_code == 422

    # Nothing got through: still PENDING, no ruling recorded.
    assert lawyer_status(auth_db, "LAWYER_0001") == "PENDING"
    assert lawyer_rule(auth_db, "LAWYER_0001") == (None, None)


# =========================================================
# 6 — SELF-APPROVAL PROTECTION
# =========================================================


def test_lawyer_cannot_reach_any_admin_route(
    client, auth_db, admin_token
):
    """The self-approval case, refused on every route — including
    the PATCH aimed at the lawyer's own row — with the same fixed
    403 every wrong-role caller gets."""
    lawyer_token = register_lawyer(client).json()["access_token"]

    forbidden = "You do not have permission to perform this action."

    listing = client.get(
        "/api/admin/lawyers", headers=auth_header(lawyer_token)
    )
    assert listing.status_code == 403
    assert listing.json()["detail"] == forbidden

    detail = client.get(
        "/api/admin/lawyers/LAWYER_0001",
        headers=auth_header(lawyer_token),
    )
    assert detail.status_code == 403

    # The self-approval attempt itself.
    own_row = client.patch(
        "/api/admin/lawyers/LAWYER_0001",
        json={"verification_status": "APPROVED"},
        headers=auth_header(lawyer_token),
    )
    assert own_row.status_code == 403
    assert own_row.json()["detail"] == forbidden

    # ...and the row is untouched.
    assert lawyer_status(auth_db, "LAWYER_0001") == "PENDING"
    assert lawyer_rule(auth_db, "LAWYER_0001") == (None, None)


def test_citizen_cannot_reach_admin_routes(client, admin_token):
    citizen_token = register_user(client).json()["access_token"]

    assert (
        client.get(
            "/api/admin/lawyers", headers=auth_header(citizen_token)
        ).status_code
        == 403
    )
    assert (
        client.patch(
            "/api/admin/lawyers/LAWYER_0001",
            json={"verification_status": "APPROVED"},
            headers=auth_header(citizen_token),
        ).status_code
        == 403
    )


def test_admin_routes_require_a_session(client):
    assert client.get("/api/admin/lawyers").status_code == 401
    assert (
        client.patch(
            "/api/admin/lawyers/LAWYER_0001",
            json={"verification_status": "APPROVED"},
        ).status_code
        == 401
    )
    assert (
        client.get(
            "/api/admin/lawyers/LAWYER_0001",
            headers={"Authorization": "Bearer not-a-real-token"},
        ).status_code
        == 401
    )


# =========================================================
# 7 — NO HASH, EVER
# =========================================================


def test_no_admin_response_carries_a_password_hash(
    client, admin_token
):
    register_lawyer(client)

    for response in (
        client.get(
            "/api/admin/lawyers", headers=auth_header(admin_token)
        ),
        client.get(
            "/api/admin/lawyers/LAWYER_0001",
            headers=auth_header(admin_token),
        ),
        client.patch(
            "/api/admin/lawyers/LAWYER_0001",
            json={"verification_status": "APPROVED"},
            headers=auth_header(admin_token),
        ),
    ):
        assert "pbkdf2" not in response.text
        assert "password_hash" not in response.text
        assert GOOD_PASSWORD not in response.text

"""Lawyer Dashboard profile endpoint — SQLite fallback + visible errors.

Run from the API folder::

    python -m pytest

Hermetic like the other suites: ``NYAYMITRA_AUTH_DB`` points at a
throwaway file per test, and the PostgreSQL directory is forced to be
unreachable so the fallback path runs deterministically even on a
machine where PostgreSQL happens to be installed.

Background — the two compounding defects behind "Unable to load your
dashboard / Failed to fetch":

 1. ``GET /api/lawyers/{id}`` (the call the dashboard makes) was
    PostgreSQL-only, and this environment has no PostgreSQL, so every
    call raised ``psycopg2.OperationalError`` and answered 500;
 2. the global ``Exception`` handler runs in Starlette's
    ServerErrorMiddleware, *outside* CORSMiddleware, so that 500 went
    out without ``Access-Control-Allow-Origin`` — the browser blocked
    the response and the UI could only show the generic
    "Failed to fetch".

Covered:

 1. the endpoint answers 200 from the account database when
    PostgreSQL is unreachable;
 2. the payload matches the frontend's Lawyer shape (full_name,
    practice_areas as an array, profile_status vocabulary);
 3. verification state is reflected after an admin approval;
 4. the account's login email is NOT exposed on this public route;
 5. unknown id -> 404, blank id -> 400 — never a 500;
 6. an unhandled 500 still carries CORS headers for an allowed
    origin, and none for a disallowed one.
"""

from __future__ import annotations

import psycopg2
import pytest
from fastapi.testclient import TestClient

from auth import security
from database.sqlite_db import connect

GOOD_PASSWORD = "password123"

ALLOWED_ORIGIN = "http://localhost:5173"
DISALLOWED_ORIGIN = "http://evil.example"


# =========================================================
# FIXTURES (same pattern as the other suites)
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


@pytest.fixture()
def pg_down(monkeypatch):
    """Force the PostgreSQL directory to be unreachable."""

    def unavailable():  # noqa: ANN001
        raise psycopg2.OperationalError(
            "connection refused (test forces this)"
        )

    monkeypatch.setattr(
        "lawyer.routes.get_db_connection", unavailable
    )


def make_admin() -> int:
    """Insert an ADMIN directly — there is no registration path."""
    connection = connect()
    try:
        cursor = connection.execute(
            """
            INSERT INTO users (name, email, password_hash, role, is_demo)
            VALUES (?, ?, ?, 'ADMIN', 0)
            """,
            (
                "Test Admin",
                "admin-profile-test@example.com",
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


# =========================================================
# HELPERS
# =========================================================


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def register_lawyer(
    client,
    email: str = "advocate@example.com",
    license_id: str = "ENR/2024/0001",
    name: str = "Test Advocate",
):
    response = client.post(
        "/api/auth/register/lawyer",
        json={
            "full_name": name,
            "email": email,
            "password": GOOD_PASSWORD,
            "password_confirmation": GOOD_PASSWORD,
            "license_id": license_id,
            "practice_areas": ["Criminal Law", "Family Law"],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["user"]["lawyer_id"]


# =========================================================
# 1-4. THE DASHBOARD ENDPOINT, POSTGRESQL UNREACHABLE
# =========================================================


def test_profile_falls_back_to_sqlite_when_postgres_is_down(
    client, auth_db, pg_down
):
    lawyer_id = register_lawyer(client)

    # Public directory route: no Authorization header.
    response = client.get(f"/api/lawyers/{lawyer_id}")

    assert response.status_code == 200, response.text
    data = response.json()

    # What the dashboard reads on first paint.
    assert data["lawyer_id"] == lawyer_id
    assert data["full_name"] == "Test Advocate"
    assert data["enrollment_number"] == "ENR/2024/0001"
    assert isinstance(data["practice_areas"], list)
    assert "Criminal Law" in data["practice_areas"]
    assert data["profile_status"] == "Pending"

    # Columns the account database does not hold arrive as the
    # null / empty shape the frontend already renders around.
    assert data["courts_of_practice"] == []
    assert data["gender"] is None
    assert "years_of_experience" in data

    # The login email is a sign-in identity, never profile data.
    assert data["professional_email"] is None


def test_profile_status_reflects_admin_approval(
    client, auth_db, pg_down, admin_token
):
    lawyer_id = register_lawyer(
        client,
        email="approving@example.com",
        license_id="ENR/2024/0002",
        name="Approved Advocate",
    )

    decision = client.patch(
        f"/api/admin/lawyers/{lawyer_id}",
        json={"verification_status": "APPROVED"},
        headers=auth_header(admin_token),
    )
    assert decision.status_code == 200, decision.text

    response = client.get(f"/api/lawyers/{lawyer_id}")
    assert response.status_code == 200, response.text
    assert response.json()["profile_status"] == "Verified"


def test_unknown_lawyer_id_is_404_not_500(client, auth_db, pg_down):
    response = client.get("/api/lawyers/LAWYER_9999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Lawyer not found"


def test_blank_lawyer_id_is_400(client, auth_db, pg_down):
    response = client.get("/api/lawyers/%20")

    assert response.status_code == 400
    assert "required" in response.json()["detail"].lower()


# =========================================================
# 5-6. A 500 MUST STILL BE READABLE BY THE BROWSER (CORS)
# =========================================================


def test_unhandled_500_carries_cors_headers_for_allowed_origin(
    client, auth_db, monkeypatch
):
    def boom():
        raise RuntimeError("simulated backend failure")

    monkeypatch.setattr("lawyer.routes.get_db_connection", boom)

    response = client.get(
        "/api/lawyers", headers={"Origin": ALLOWED_ORIGIN}
    )

    assert response.status_code == 500
    assert "detail" in response.json()
    assert (
        response.headers.get("access-control-allow-origin")
        == ALLOWED_ORIGIN
    )


def test_unhandled_500_has_no_cors_headers_for_disallowed_origin(
    client, auth_db, monkeypatch
):
    def boom():
        raise RuntimeError("simulated backend failure")

    monkeypatch.setattr("lawyer.routes.get_db_connection", boom)

    response = client.get(
        "/api/lawyers", headers={"Origin": DISALLOWED_ORIGIN}
    )

    assert response.status_code == 500
    assert "access-control-allow-origin" not in response.headers

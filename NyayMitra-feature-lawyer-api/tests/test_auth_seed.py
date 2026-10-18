"""Demo-account seeder — idempotency, hashing and labelling.

Run from the API folder::

    python -m pytest tests/test_auth_seed.py

Like ``test_auth_api.py``, every test runs against its own throwaway
SQLite file: the seeder is exercised exactly as it would run against
the development database, but the development database is never
touched by the test suite.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from auth import security
from database.seed_demo_accounts import DEMO_ACCOUNTS, DEMO_LAWYER, seed


# =========================================================
# FIXTURES
# =========================================================


@pytest.fixture(scope="session")
def app():
    from main import app as application

    return application


@pytest.fixture()
def auth_db(tmp_path, monkeypatch):
    path = tmp_path / "seeded.db"
    monkeypatch.setenv("NYAYMITRA_AUTH_DB", str(path))
    return path


def read_all(path) -> list[sqlite3.Row]:  # noqa: ANN001
    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute("SELECT * FROM users ORDER BY id").fetchall()
        return rows
    finally:
        connection.close()


# =========================================================
# IDEMPOTENT SEED
# =========================================================


def test_seed_creates_the_demo_accounts_and_is_idempotent(auth_db):
    first = seed()
    second = seed()

    # First run creates all three; second run creates nothing new.
    assert sorted(first["created"]) == sorted(
        account["email"] for account in DEMO_ACCOUNTS
    )
    assert first["lawyer_created"] is True

    assert second["created"] == []
    assert sorted(second["restored"]) == sorted(
        account["email"] for account in DEMO_ACCOUNTS
    )
    assert second["lawyer_created"] is False
    assert second["lawyer_status"] == DEMO_LAWYER["verification_status"]

    users = read_all(auth_db)

    # Exactly three users — no duplicates after two runs.
    assert len(users) == 3

    roles = {row["email"]: row["role"] for row in users}
    assert roles == {
        "asha@example.com": "USER",
        "rohan@example.com": "LAWYER",
        "admin@nyaymitra.in": "ADMIN",
    }

    # Clearly identified as demo/test accounts.
    assert all(row["is_demo"] == 1 for row in users)


def test_seed_stores_only_pbkdf2_hashes(auth_db):
    seed()

    users = read_all(auth_db)
    prefix = f"pbkdf2_sha256${security.PBKDF2_ITERATIONS}$"

    for row in users:
        assert row["password_hash"].startswith(prefix)

    # Plaintext demo passwords live in this file's documentation and
    # README — never in the database bytes.
    chunks = []
    for path in sorted(Path(auth_db).parent.iterdir()):
        if path.is_file():
            chunks.append(path.read_bytes())
    raw = b"".join(chunks)

    for account in DEMO_ACCOUNTS:
        assert account["password"].encode() not in raw


def test_seed_lawyer_row_is_approved_and_linked_to_admin(auth_db):
    seed()

    connection = sqlite3.connect(str(auth_db))
    connection.row_factory = sqlite3.Row
    try:
        lawyer = connection.execute(
            "SELECT * FROM lawyers WHERE lawyer_id = ?",
            (DEMO_LAWYER["lawyer_id"],),
        ).fetchone()
        admin = connection.execute(
            "SELECT id FROM users WHERE email = ?",
            (DEMO_LAWYER["admin_email"],),
        ).fetchone()
        lawyer_user = connection.execute(
            "SELECT id FROM users WHERE email = ?",
            (DEMO_LAWYER["lawyer_email"],),
        ).fetchone()
    finally:
        connection.close()

    assert lawyer is not None
    assert lawyer["verification_status"] == "APPROVED"
    assert lawyer["user_id"] == lawyer_user["id"]
    assert lawyer["verified_by"] == admin["id"]
    assert lawyer["license_id"] == DEMO_LAWYER["license_id"]


def test_reseeding_never_undoes_an_admin_decision(auth_db):
    """Re-running the seeder must not flip a lawyer back to APPROVED
    after an admin rejected them."""
    seed()

    connection = sqlite3.connect(str(auth_db))
    try:
        connection.execute(
            "UPDATE lawyers SET verification_status = 'REJECTED'"
            " WHERE lawyer_id = ?",
            (DEMO_LAWYER["lawyer_id"],),
        )
        connection.commit()
    finally:
        connection.close()

    summary = seed()
    assert summary["lawyer_status"] == "REJECTED"

    connection = sqlite3.connect(str(auth_db))
    try:
        status = connection.execute(
            "SELECT verification_status FROM lawyers WHERE lawyer_id = ?",
            (DEMO_LAWYER["lawyer_id"],),
        ).fetchone()[0]
    finally:
        connection.close()

    assert status == "REJECTED"


def test_demo_lawyer_logs_in_with_lawyer_id(app, auth_db):
    """The seeded lawyer account signs in through the normal endpoint
    and carries its lawyer_id for the dashboard/chat hand-off."""
    seed()

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/api/auth/login",
        json={"email": "rohan@example.com", "password": "lawyer123"},
    )

    assert response.status_code == 200

    user = response.json()["user"]
    assert user["role"] == "LAWYER"
    assert user["lawyer_id"] == DEMO_LAWYER["lawyer_id"]
    assert user["is_demo"] is True
    assert "pbkdf2" not in response.text


def test_seeded_admin_can_open_the_admin_session(app, auth_db):
    """The Admin Dashboard teammate can authenticate an ADMIN session
    against the seeded account (there is no self-registration path)."""
    seed()

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/api/auth/login",
        json={"email": "admin@nyaymitra.in", "password": "admin123"},
    )

    assert response.status_code == 200

    token = response.json()["access_token"]
    me = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert me.status_code == 200
    assert me.json()["role"] == "ADMIN"
    assert me.json()["is_demo"] is True

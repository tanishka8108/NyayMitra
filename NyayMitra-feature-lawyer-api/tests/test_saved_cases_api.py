"""Server-side My Cases — save, list, remove, ownership, persistence.

Run from the API folder::

    python -m pytest

Hermetic like the other suites: ``NYAYMITRA_AUTH_DB`` points at a
throwaway file per test, so nothing here touches the development
database or the browser's own saved rows.

Covered, in the order the brief lists it:

 1. every endpoint answers 401 when signed out;
 2. a signed-in account saves a CNR the service can actually read;
 3. a second save of the same CNR does not create a second row;
 4. the list comes back with the real case record attached;
 5. saved cases persist in the database, not in the request;
 6. a malformed CNR is refused with 400 and writes nothing;
 7. an unknown CNR is refused with 404 and leaves no orphan row;
 8. removal works, and removing twice is 404 not 500;
 9. one account cannot see or remove another account's save;
10. a client-supplied user id in the body is ignored — the owner
    comes from the session, never from the request;
11. an account that saved nothing gets a normal empty 200.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from auth import security
from database.sqlite_db import connect

GOOD_PASSWORD = "password123"

# Present in the development dataset (dev_data/MHPU210000042026_...).
KNOWN_CNR = "MHPU210000042026"

# Well-formed CNR shape that the provider has no record for.
UNKNOWN_CNR = "ZZZZ999999999999"


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


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def register_user(client, email: str, name: str = "Test Citizen") -> tuple[str, int]:
    response = client.post(
        "/api/auth/register",
        json={
            "full_name": name,
            "email": email,
            "password": GOOD_PASSWORD,
            "password_confirmation": GOOD_PASSWORD,
        },
    )
    assert response.status_code == 201
    data = response.json()
    return data["access_token"], data["user"]["user_id"]


@pytest.fixture()
def citizen(client):
    return register_user(client, "citizen@example.com")


@pytest.fixture()
def other_citizen(client):
    return register_user(client, "neighbour@example.com", "Neighbour")


# =========================================================
# 1. AUTHENTICATION
# =========================================================


def test_every_endpoint_requires_a_session(client):
    assert client.get("/api/saved-cases").status_code == 401
    assert (
        client.post("/api/saved-cases", json={"cnr_number": KNOWN_CNR}).status_code
        == 401
    )
    assert client.delete(f"/api/saved-cases/{KNOWN_CNR}").status_code == 401

    # A forged bearer token is 401, not a partial answer.
    assert (
        client.get(
            "/api/saved-cases", headers=auth_header("not-a-real-token")
        ).status_code
        == 401
    )


# =========================================================
# 2–4. SAVE, DEDUPLICATE, LIST
# =========================================================


def test_save_then_list_returns_the_real_record(client, citizen):
    token, user_id = citizen

    created = client.post(
        "/api/saved-cases",
        json={"cnr_number": KNOWN_CNR},
        headers=auth_header(token),
    )
    assert created.status_code == 201
    body = created.json()
    assert body["success"] is True
    assert body["already_saved"] is False
    assert body["item"]["cnr_number"] == KNOWN_CNR

    listing = client.get("/api/saved-cases", headers=auth_header(token))
    assert listing.status_code == 200
    payload = listing.json()

    assert payload["success"] is True
    assert payload["total"] == 1
    assert payload["items"][0]["cnr_number"] == KNOWN_CNR

    # The record is joined from the provider, not a stored copy.
    record = payload["items"][0]["case"]
    assert record is not None
    assert record["cnr_number"] == KNOWN_CNR
    assert payload["data_source"]["available"] is True


def test_duplicate_save_never_grows_the_list(client, citizen):
    token, _user_id = citizen

    for expected_status in (201, 200):
        response = client.post(
            "/api/saved-cases",
            json={"cnr_number": KNOWN_CNR},
            headers=auth_header(token),
        )
        assert response.status_code == expected_status

    second = response.json()
    assert second["already_saved"] is True

    listing = client.get("/api/saved-cases", headers=auth_header(token))
    assert listing.json()["total"] == 1


def test_saving_is_idempotent_even_when_repeated_many_times(client, citizen):
    token, _user_id = citizen

    for _ in range(3):
        client.post(
            "/api/saved-cases",
            json={"cnr_number": KNOWN_CNR},
            headers=auth_header(token),
        )

    assert client.get("/api/saved-cases", headers=auth_header(token)).json()[
        "total"
    ] == 1


# =========================================================
# 5. PERSISTENCE
# =========================================================


def test_saved_case_is_written_to_the_database_not_the_request(client, citizen):
    token, user_id = citizen

    client.post(
        "/api/saved-cases",
        json={"cnr_number": KNOWN_CNR},
        headers=auth_header(token),
    )

    # Read the row straight out of SQLite with a brand-new connection —
    # nothing about the HTTP request is involved.
    connection = connect()
    try:
        rows = connection.execute(
            "SELECT user_id, cnr_number FROM saved_cases"
        ).fetchall()
    finally:
        connection.close()

    assert len(rows) == 1
    assert rows[0]["user_id"] == user_id
    assert rows[0]["cnr_number"] == KNOWN_CNR


def test_saved_case_survives_a_new_session(client, citizen):
    token, user_id = citizen

    client.post(
        "/api/saved-cases",
        json={"cnr_number": KNOWN_CNR},
        headers=auth_header(token),
    )

    # A completely fresh login — a stand-in for closing and reopening
    # the app — must still see the same shortlist.
    new_token = security.create_session(user_id)
    listing = client.get("/api/saved-cases", headers=auth_header(new_token))
    assert listing.status_code == 200
    assert listing.json()["total"] == 1


# =========================================================
# 6–7. VALIDATION, NO ORPHANS
# =========================================================


def test_malformed_cnr_is_refused_and_writes_nothing(client, citizen):
    token, _user_id = citizen

    bad = client.post(
        "/api/saved-cases",
        json={"cnr_number": "not-a-cnr"},
        headers=auth_header(token),
    )
    assert bad.status_code == 400
    assert "detail" in bad.json()

    assert client.get("/api/saved-cases", headers=auth_header(token)).json()[
        "total"
    ] == 0


def test_blank_cnr_is_refused(client, citizen):
    token, _user_id = citizen

    blank = client.post(
        "/api/saved-cases",
        json={"cnr_number": "   "},
        headers=auth_header(token),
    )
    assert blank.status_code in (400, 422)


def test_unknown_cnr_is_404_and_leaves_no_orphan_row(client, citizen):
    token, _user_id = citizen

    unknown = client.post(
        "/api/saved-cases",
        json={"cnr_number": UNKNOWN_CNR},
        headers=auth_header(token),
    )
    assert unknown.status_code == 404
    assert "detail" in unknown.json()

    # The rejected save must not have left a half-written row behind.
    connection = connect()
    try:
        count = connection.execute(
            "SELECT COUNT(*) AS n FROM saved_cases"
        ).fetchone()["n"]
    finally:
        connection.close()
    assert count == 0

    assert client.get("/api/saved-cases", headers=auth_header(token)).json()[
        "total"
    ] == 0


# =========================================================
# 8. REMOVAL
# =========================================================


def test_remove_own_case_then_remove_again(client, citizen):
    token, _user_id = citizen

    client.post(
        "/api/saved-cases",
        json={"cnr_number": KNOWN_CNR},
        headers=auth_header(token),
    )

    removed = client.delete(
        f"/api/saved-cases/{KNOWN_CNR}", headers=auth_header(token)
    )
    assert removed.status_code == 200
    assert removed.json()["removed"] is True

    assert client.get("/api/saved-cases", headers=auth_header(token)).json()[
        "total"
    ] == 0

    # Removing something that is not there is 404, not a 500.
    again = client.delete(
        f"/api/saved-cases/{KNOWN_CNR}", headers=auth_header(token)
    )
    assert again.status_code == 404


def test_removing_a_malformed_cnr_is_400(client, citizen):
    token, _user_id = citizen
    response = client.delete(
        "/api/saved-cases/nope", headers=auth_header(token)
    )
    assert response.status_code == 400


# =========================================================
# 9. OWNERSHIP — one account cannot reach another's list
# =========================================================


def test_citizen_cannot_see_or_delete_a_neighbours_save(
    client, citizen, other_citizen
):
    token, _user_id = citizen
    other_token, _other_id = other_citizen

    client.post(
        "/api/saved-cases",
        json={"cnr_number": KNOWN_CNR},
        headers=auth_header(token),
    )

    # B's own list is unaffected by A's save.
    neighbour_list = client.get(
        "/api/saved-cases", headers=auth_header(other_token)
    )
    assert neighbour_list.status_code == 200
    assert neighbour_list.json()["total"] == 0

    # B cannot delete A's row — and gets 404 rather than 403, so the
    # answer never confirms the row exists.
    blocked = client.delete(
        f"/api/saved-cases/{KNOWN_CNR}", headers=auth_header(other_token)
    )
    assert blocked.status_code == 404

    # A still has it.
    assert client.get("/api/saved-cases", headers=auth_header(token)).json()[
        "total"
    ] == 1


def test_two_accounts_can_save_the_same_cnr_independently(
    client, citizen, other_citizen
):
    token, _user_id = citizen
    other_token, _other_id = other_citizen

    first = client.post(
        "/api/saved-cases",
        json={"cnr_number": KNOWN_CNR},
        headers=auth_header(token),
    )
    second = client.post(
        "/api/saved-cases",
        json={"cnr_number": KNOWN_CNR},
        headers=auth_header(other_token),
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["already_saved"] is False

    assert client.get("/api/saved-cases", headers=auth_header(token)).json()[
        "total"
    ] == 1
    assert client.get(
        "/api/saved-cases", headers=auth_header(other_token)
    ).json()["total"] == 1


# =========================================================
# 10. THE OWNER COMES FROM THE SESSION, NOT THE BODY
# =========================================================


def test_a_client_supplied_user_id_is_ignored(client, citizen, other_citizen):
    token, user_id = citizen
    _other_token, other_id = other_citizen

    # The caller tries to make the row belong to somebody else. The
    # request model has no such field, so it cannot land anywhere.
    response = client.post(
        "/api/saved-cases",
        json={
            "cnr_number": KNOWN_CNR,
            "user_id": other_id,
            "owner_user_id": other_id,
            "role": "ADMIN",
        },
        headers=auth_header(token),
    )
    assert response.status_code == 201

    connection = connect()
    try:
        row = connection.execute(
            "SELECT user_id FROM saved_cases WHERE cnr_number = ?",
            (KNOWN_CNR,),
        ).fetchone()
    finally:
        connection.close()

    assert row is not None
    assert row["user_id"] == user_id, "ownership must come from the session"


def test_list_never_leaks_another_accounts_row(client, citizen, other_citizen):
    token, _user_id = citizen
    other_token, _other_id = other_citizen

    client.post(
        "/api/saved-cases",
        json={"cnr_number": KNOWN_CNR},
        headers=auth_header(token),
    )

    payload = client.get(
        "/api/saved-cases", headers=auth_header(other_token)
    ).json()
    assert payload["items"] == []
    assert payload["total"] == 0


# =========================================================
# 11. EMPTY STATE
# =========================================================


def test_an_account_that_saved_nothing_gets_a_normal_empty_200(client, citizen):
    token, _user_id = citizen

    listing = client.get("/api/saved-cases", headers=auth_header(token))
    assert listing.status_code == 200

    payload = listing.json()
    assert payload["success"] is True
    assert payload["items"] == []
    assert payload["total"] == 0

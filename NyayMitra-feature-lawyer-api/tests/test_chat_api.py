"""USER ↔ LAWYER chat — Phase 3.

Run from the API folder::

    python -m pytest

Hermetic like the other suites: ``NYAYMITRA_AUTH_DB`` points at a
throwaway file per test, so nothing here touches the development
database.

Covered, in the order the brief lists it:

 1. a user can list the approved (verified) lawyers available;
 2. a PENDING lawyer is not in that list;
 3. a REJECTED lawyer is not in that list;
 4. a user can start a conversation with an approved lawyer;
 5. an existing conversation is reused, never duplicated;
 6. the user can send a message;
 7. the lawyer can load the conversation;
 8. the lawyer can reply;
 9. the user can load the reply;
10. messages persist across re-login (server-side storage);
11. user A cannot read or write user B's conversation;
12. lawyer A cannot read or write lawyer B's conversation;
13. a user cannot impersonate another user through the payload;
14. a lawyer cannot impersonate another lawyer through the payload;
15. a PENDING lawyer cannot use verified-lawyer chat;
16. a REJECTED lawyer cannot use verified-lawyer chat;
17. every chat endpoint answers 401 when signed out;
18. invalid conversation ids are handled safely (no 500);
19/20. the pre-existing auth / CNR-cases suites stay green —
      asserted by running the whole battery (this file's fixtures
      use the same hermetic pattern, so a regression there fails
      the run).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from auth import security
from database.sqlite_db import connect

GOOD_PASSWORD = "password123"

CNR = "MHPU210000042026"


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


@pytest.fixture()
def admin_token(auth_db) -> str:
    """An ADMIN session — there is no registration path to ADMIN."""
    connection = connect()
    try:
        cursor = connection.execute(
            """
            INSERT INTO users (name, email, password_hash, role, is_demo)
            VALUES (?, ?, ?, 'ADMIN', 0)
            """,
            (
                "Test Admin",
                "admin@nyaymitra.in",
                security.hash_password(GOOD_PASSWORD),
            ),
        )
        connection.commit()
        admin_id = int(cursor.lastrowid)
    finally:
        connection.close()

    return security.create_session(admin_id)


# =========================================================
# HELPERS
# =========================================================


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def register_user(
    client,
    email: str = "citizen@example.com",
    name: str = "Test Citizen",
) -> tuple[str, int]:
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


def register_lawyer(
    client,
    email: str = "advocate@example.com",
    license_id: str = "ENR/2024/0001",
    name: str = "Test Advocate",
) -> tuple[str, str]:
    """Returns ``(token, lawyer_id)`` — always PENDING."""
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
    assert response.status_code == 201
    data = response.json()
    return data["access_token"], data["user"]["lawyer_id"]


def approve(client, admin_token: str, lawyer_id: str) -> None:
    response = client.patch(
        f"/api/admin/lawyers/{lawyer_id}",
        headers=auth_header(admin_token),
        json={"verification_status": "APPROVED"},
    )
    assert response.status_code == 200, response.text


def reject(client, admin_token: str, lawyer_id: str) -> None:
    response = client.patch(
        f"/api/admin/lawyers/{lawyer_id}",
        headers=auth_header(admin_token),
        json={"verification_status": "REJECTED"},
    )
    assert response.status_code == 200, response.text


def approved_lawyer(
    client,
    admin_token: str,
    email: str = "advocate@example.com",
    license_id: str = "ENR/2024/0001",
    name: str = "Test Advocate",
) -> tuple[str, str]:
    token, lawyer_id = register_lawyer(
        client, email=email, license_id=license_id, name=name
    )
    approve(client, admin_token, lawyer_id)
    return token, lawyer_id


def open_thread(
    client,
    user_token: str,
    lawyer_id: str,
    case_cnr: str | None = None,
):
    payload: dict = {"lawyer_id": lawyer_id}
    if case_cnr:
        payload["case_cnr"] = case_cnr
    return client.post(
        "/api/chat/conversations",
        headers=auth_header(user_token),
        json=payload,
    )


def send(client, token: str, conversation_id: int, message: str):
    return client.post(
        f"/api/chat/conversations/{conversation_id}/messages",
        headers=auth_header(token),
        json={"message": message},
    )


# =========================================================
# 1–3  VERIFIED LAWYER DIRECTORY
# =========================================================


def test_user_lists_approved_lawyers(client, admin_token):
    lawyer_token, lawyer_id = approved_lawyer(client, admin_token)
    user_token, _user_id = register_user(client)

    response = client.get(
        "/api/chat/lawyers",
        headers=auth_header(user_token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1

    entry = body["lawyers"][0]
    assert entry["lawyer_id"] == lawyer_id
    assert entry["full_name"] == "Test Advocate"
    assert entry["practice_areas"] == ["Criminal Law", "Family Law"]
    assert entry["verification_status"] == "APPROVED"

    # Public half of a profile only — no personal contact details.
    assert "email" not in entry
    assert "license_id" not in entry
    assert "professional_phone_number" not in entry

    # The approved lawyer's own session sees the directory too.
    assert lawyer_token


def test_pending_lawyer_not_listed(client):
    _token, pending_id = register_lawyer(
        client,
        email="pending@example.com",
        license_id="ENR/2024/0002",
    )
    _utoken, _uid = register_user(client)

    response = client.get(
        "/api/chat/lawyers",
        headers=auth_header(_utoken),
    )

    assert response.status_code == 200
    ids = [entry["lawyer_id"] for entry in response.json()["lawyers"]]
    assert pending_id not in ids
    assert response.json()["count"] == 0


def test_rejected_lawyer_not_listed(client, admin_token):
    _token, rejected_id = register_lawyer(
        client,
        email="rejected@example.com",
        license_id="ENR/2024/0003",
    )
    reject(client, admin_token, rejected_id)

    _utoken, _uid = register_user(client)
    response = client.get(
        "/api/chat/lawyers",
        headers=auth_header(_utoken),
    )

    assert response.status_code == 200
    ids = [entry["lawyer_id"] for entry in response.json()["lawyers"]]
    assert rejected_id not in ids


# =========================================================
# 4–10  THE HAPPY PATH, END TO END
# =========================================================


def test_user_starts_conversation_with_approved_lawyer(
    client, admin_token
):
    _ltoken, lawyer_id = approved_lawyer(client, admin_token)
    user_token, user_id = register_user(client)

    response = open_thread(client, user_token, lawyer_id, CNR)

    assert response.status_code == 201, response.text
    thread = response.json()
    assert thread["user_id"] == user_id
    assert thread["lawyer_id"] == lawyer_id
    assert thread["case_cnr"] == CNR
    assert thread["messages"] == []


def test_pending_lawyer_cannot_be_targeted_and_404_looks_like_unknown(
    client, admin_token
):
    _t, pending_id = register_lawyer(
        client,
        email="pending@example.com",
        license_id="ENR/2024/0002",
    )
    user_token, _uid = register_user(client)

    pending = open_thread(client, user_token, pending_id)
    unknown = open_thread(client, user_token, "LAWYER_9999")

    # Same status and same sentence: neither existence nor
    # verification state leaks through this endpoint.
    assert pending.status_code == unknown.status_code == 404
    assert pending.json() == unknown.json()


def test_existing_conversation_is_reused(client, admin_token):
    _ltoken, lawyer_id = approved_lawyer(client, admin_token)
    user_token, _uid = register_user(client)

    first = open_thread(client, user_token, lawyer_id, CNR)
    second = open_thread(client, user_token, lawyer_id)

    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]

    listing = client.get(
        "/api/chat/conversations",
        headers=auth_header(user_token),
    )
    assert listing.json()["count"] == 1


def test_user_sends_message(client, admin_token):
    _ltoken, lawyer_id = approved_lawyer(client, admin_token)
    user_token, user_id = register_user(client)
    thread = open_thread(client, user_token, lawyer_id).json()

    response = send(client, user_token, thread["id"], "Namaste.")

    assert response.status_code == 201, response.text
    message = response.json()
    assert message["sender_id"] == user_id
    assert message["sender_role"] == "USER"
    assert message["message"] == "Namaste."


def test_lawyer_loads_conversation(client, admin_token):
    _ltoken, lawyer_id = approved_lawyer(client, admin_token)
    user_token, _uid = register_user(client, name="Asha Verma")
    thread = open_thread(client, user_token, lawyer_id).json()
    send(client, user_token, thread["id"], "Please review my case.")

    listing = client.get(
        "/api/chat/lawyer/conversations",
        headers=auth_header(_ltoken),
    )

    assert listing.status_code == 200
    body = listing.json()
    assert body["count"] == 1

    loaded = body["conversations"][0]
    assert loaded["id"] == thread["id"]
    assert loaded["user_name"] == "Asha Verma"
    assert len(loaded["messages"]) == 1
    assert loaded["messages"][0]["message"] == "Please review my case."


def test_lawyer_replies_and_user_loads_reply(client, admin_token):
    lawyer_token, lawyer_id = approved_lawyer(client, admin_token)
    user_token, user_id = register_user(client)
    thread = open_thread(client, user_token, lawyer_id).json()
    send(client, user_token, thread["id"], "Hello Adv.")

    reply = send(client, lawyer_token, thread["id"], "How can I help?")

    assert reply.status_code == 201, reply.text
    assert reply.json()["sender_role"] == "LAWYER"
    assert reply.json()["sender_id"] != user_id

    history = client.get(
        f"/api/chat/conversations/{thread['id']}/messages",
        headers=auth_header(user_token),
    )

    assert history.status_code == 200
    messages = history.json()["messages"]
    assert history.json()["count"] == 2
    assert [m["sender_role"] for m in messages] == ["USER", "LAWYER"]
    assert messages[1]["message"] == "How can I help?"


def test_messages_persist_after_relogin(client, admin_token):
    _ltoken, lawyer_id = approved_lawyer(client, admin_token)
    user_token, _uid = register_user(client)
    thread = open_thread(client, user_token, lawyer_id).json()
    send(client, user_token, thread["id"], "Still here?")

    relogin = client.post(
        "/api/auth/login",
        json={
            "email": "citizen@example.com",
            "password": GOOD_PASSWORD,
        },
    )
    assert relogin.status_code == 200
    fresh_token = relogin.json()["access_token"]

    history = client.get(
        f"/api/chat/conversations/{thread['id']}/messages",
        headers=auth_header(fresh_token),
    )

    assert history.status_code == 200
    assert history.json()["count"] == 1
    assert history.json()["messages"][0]["message"] == "Still here?"


# =========================================================
# 11–14  ID TAMPERING
# =========================================================


def test_user_cannot_access_another_users_conversation(
    client, admin_token
):
    _ltoken, lawyer_id = approved_lawyer(client, admin_token)
    user_a, _a_id = register_user(client, email="a@example.com")
    user_b, _b_id = register_user(client, email="b@example.com")
    thread = open_thread(client, user_a, lawyer_id).json()
    send(client, user_a, thread["id"], "Private to A.")

    read = client.get(
        f"/api/chat/conversations/{thread['id']}",
        headers=auth_header(user_b),
    )
    messages = client.get(
        f"/api/chat/conversations/{thread['id']}/messages",
        headers=auth_header(user_b),
    )
    write = send(client, user_b, thread["id"], "Let me in.")

    # 404, not 403: B must not learn the thread exists.
    assert read.status_code == 404
    assert messages.status_code == 404
    assert write.status_code == 404
    assert read.json()["detail"] == "Conversation not found."


def test_lawyer_cannot_access_another_lawyers_conversation(
    client, admin_token
):
    _t1, lawyer_1 = approved_lawyer(
        client, admin_token, email="adv1@example.com",
        license_id="ENR/2024/0001",
    )
    token_2, lawyer_2 = approved_lawyer(
        client, admin_token, email="adv2@example.com",
        license_id="ENR/2024/0002", name="Second Advocate",
    )
    user_token, _uid = register_user(client)
    thread = open_thread(client, user_token, lawyer_1).json()

    read = client.get(
        f"/api/chat/conversations/{thread['id']}",
        headers=auth_header(token_2),
    )
    write = send(client, token_2, thread["id"], "Hopin' in.")

    assert read.status_code == 404
    assert write.status_code == 404

    # And lawyer 2's own inbox stays empty.
    listing = client.get(
        "/api/chat/lawyer/conversations",
        headers=auth_header(token_2),
    )
    assert listing.json()["count"] == 0
    assert lawyer_2 != lawyer_1


def test_user_cannot_impersonate_another_user(client, admin_token):
    _ltoken, lawyer_id = approved_lawyer(client, admin_token)
    user_a, a_id = register_user(client, email="a@example.com")
    _user_b, b_id = register_user(client, email="b@example.com")

    # A names B in the payload: the request model refuses outright.
    smuggled = client.post(
        "/api/chat/conversations",
        headers=auth_header(user_a),
        json={"lawyer_id": lawyer_id, "user_id": b_id},
    )
    assert smuggled.status_code == 422

    # A tries to use the lawyer-side creation endpoint at all.
    lawyer_side = client.post(
        "/api/chat/lawyer/conversations",
        headers=auth_header(user_a),
        json={"user_id": b_id},
    )
    assert lawyer_side.status_code == 403

    # Whatever A does, the thread written belongs to A.
    created = open_thread(client, user_a, lawyer_id)
    assert created.status_code == 201
    assert created.json()["user_id"] == a_id
    assert created.json()["user_id"] != b_id


def test_lawyer_cannot_impersonate_another_lawyer(
    client, admin_token
):
    token_1, lawyer_1 = approved_lawyer(
        client, admin_token, email="adv1@example.com",
        license_id="ENR/2024/0001",
    )
    _t2, lawyer_2 = approved_lawyer(
        client, admin_token, email="adv2@example.com",
        license_id="ENR/2024/0002", name="Second Advocate",
    )
    user_token, user_id = register_user(client)

    # lawyer_1 tries to write a colleague's id into the payload.
    smuggled = client.post(
        "/api/chat/lawyer/conversations",
        headers=auth_header(token_1),
        json={"user_id": user_id, "lawyer_id": lawyer_2},
    )
    assert smuggled.status_code == 422

    created = client.post(
        "/api/chat/lawyer/conversations",
        headers=auth_header(token_1),
        json={"user_id": user_id},
    )
    assert created.status_code == 201
    assert created.json()["lawyer_id"] == lawyer_1
    assert created.json()["lawyer_id"] != lawyer_2

    # A user-side payload naming a lawyer id is equally refused.
    user_side = client.post(
        "/api/chat/conversations",
        headers=auth_header(token_1),
        json={"lawyer_id": lawyer_2},
    )
    assert user_side.status_code == 403


# =========================================================
# 15–17  VERIFICATION GATE + SIGNED-OUT
# =========================================================


def test_pending_lawyer_cannot_use_verified_chat(client, admin_token):
    pending_token, _pid = register_lawyer(
        client,
        email="pending@example.com",
        license_id="ENR/2024/0002",
    )

    listing = client.get(
        "/api/chat/lawyer/conversations",
        headers=auth_header(pending_token),
    )
    create = client.post(
        "/api/chat/lawyer/conversations",
        headers=auth_header(pending_token),
        json={"user_id": 1},
    )
    read = client.get(
        "/api/chat/conversations/1",
        headers=auth_header(pending_token),
    )
    write = send(client, pending_token, 1, "Hi.")

    for response in (listing, create, read, write):
        assert response.status_code == 403
        assert response.json()["detail"] == (
            "Your lawyer registration is pending approval."
        )


def test_rejected_lawyer_cannot_use_verified_chat(client, admin_token):
    rejected_token, rejected_id = register_lawyer(
        client,
        email="rejected@example.com",
        license_id="ENR/2024/0003",
    )
    reject(client, admin_token, rejected_id)

    listing = client.get(
        "/api/chat/lawyer/conversations",
        headers=auth_header(rejected_token),
    )
    create = client.post(
        "/api/chat/lawyer/conversations",
        headers=auth_header(rejected_token),
        json={"user_id": 1},
    )
    read = client.get(
        "/api/chat/conversations/1",
        headers=auth_header(rejected_token),
    )

    for response in (listing, create, read):
        assert response.status_code == 403
        assert response.json()["detail"] == (
            "Your lawyer registration has been rejected."
        )


def test_signed_out_returns_401_everywhere(client, admin_token):
    _ltoken, lawyer_id = approved_lawyer(client, admin_token)
    user_token, _uid = register_user(client)
    thread = open_thread(client, user_token, lawyer_id).json()

    calls = [
        ("GET", "/api/chat/lawyers"),
        ("GET", "/api/chat/conversations"),
        ("GET", "/api/chat/lawyer/conversations"),
        ("GET", f"/api/chat/conversations/{thread['id']}"),
        ("GET", f"/api/chat/conversations/{thread['id']}/messages"),
        ("GET", "/api/chat/conversations/999999"),
    ]

    for method, path in calls:
        response = client.request(method, path)
        assert response.status_code == 401, path
        assert "WWW-Authenticate" in response.headers, path

    for path in (
        "/api/chat/conversations",
        "/api/chat/lawyer/conversations",
        f"/api/chat/conversations/{thread['id']}/messages",
    ):
        response = client.post(path, json={"message": "Hi."})
        assert response.status_code == 401, path


def test_admin_has_no_chat_surface(client, admin_token):
    response = client.get(
        "/api/chat/conversations",
        headers=auth_header(admin_token),
    )
    assert response.status_code == 403

    lawyer_side = client.get(
        "/api/chat/lawyer/conversations",
        headers=auth_header(admin_token),
    )
    assert lawyer_side.status_code == 403

    send_attempt = client.post(
        "/api/chat/conversations/1/messages",
        headers=auth_header(admin_token),
        json={"message": "Admin note."},
    )
    assert send_attempt.status_code == 403
    assert send_attempt.json()["detail"] == (
        "You do not have permission to perform this action."
    )


# =========================================================
# 18  INVALID INPUT, SAFELY
# =========================================================


def test_invalid_conversation_id_is_handled_safely(
    client, admin_token
):
    _ltoken, lawyer_id = approved_lawyer(client, admin_token)
    user_token, _uid = register_user(client)

    missing = client.get(
        "/api/chat/conversations/999999",
        headers=auth_header(user_token),
    )
    not_a_number = client.get(
        "/api/chat/conversations/not-a-number",
        headers=auth_header(user_token),
    )
    missing_messages = client.get(
        "/api/chat/conversations/999999/messages",
        headers=auth_header(user_token),
    )

    assert missing.status_code == 404
    assert missing_messages.status_code == 404
    # A malformed id never reaches the database as a raw string.
    assert not_a_number.status_code == 422


def test_message_validation(client, admin_token):
    _ltoken, lawyer_id = approved_lawyer(client, admin_token)
    user_token, _uid = register_user(client)
    thread = open_thread(client, user_token, lawyer_id).json()

    blank = send(client, user_token, thread["id"], "   ")
    oversized = send(client, user_token, thread["id"], "x" * 4001)
    extra_field = client.post(
        f"/api/chat/conversations/{thread['id']}/messages",
        headers=auth_header(user_token),
        json={"message": "Hi.", "sender_id": 999},
    )

    assert blank.status_code == 400
    assert oversized.status_code == 400
    # No sender field can be smuggled in — extra=forbid.
    assert extra_field.status_code == 422

    history = client.get(
        f"/api/chat/conversations/{thread['id']}/messages",
        headers=auth_header(user_token),
    )
    assert history.json()["count"] == 0


def test_case_cnr_link_is_validated_and_normalized(
    client, admin_token
):
    _ltoken, lawyer_id = approved_lawyer(client, admin_token)
    user_token, _uid = register_user(client)

    lower = open_thread(
        client, user_token, lawyer_id, CNR.lower()
    )
    assert lower.status_code == 201
    assert lower.json()["case_cnr"] == CNR

    # The CNR is checked before anything else touches the request —
    # a malformed one is a clean 400 and stores nothing.
    invalid = open_thread(client, user_token, lawyer_id, "not-a-cnr")
    assert invalid.status_code == 400

    injection = open_thread(
        client, user_token, lawyer_id, "'; DROP TABLE messages;--"
    )
    assert injection.status_code == 400


def test_lawyer_conversation_requires_a_real_client(
    client, admin_token
):
    lawyer_token, _lawyer_id = approved_lawyer(client, admin_token)

    unknown = client.post(
        "/api/chat/lawyer/conversations",
        headers=auth_header(lawyer_token),
        json={"user_id": 424242},
    )
    assert unknown.status_code == 404
    assert unknown.json()["detail"] == "Account not found."


def test_user_list_is_scoped_to_the_caller(client, admin_token):
    _ltoken, lawyer_id = approved_lawyer(client, admin_token)
    user_a, _a = register_user(client, email="a@example.com")
    user_b, _b = register_user(client, email="b@example.com")

    open_thread(client, user_a, lawyer_id)

    a_list = client.get(
        "/api/chat/conversations",
        headers=auth_header(user_a),
    )
    b_list = client.get(
        "/api/chat/conversations",
        headers=auth_header(user_b),
    )

    assert a_list.json()["count"] == 1
    assert b_list.json()["count"] == 0

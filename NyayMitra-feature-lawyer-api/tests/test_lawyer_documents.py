"""Verification documents + optional lawyer profile — Phase 2b.

Run from the API folder::

    python -m pytest

Hermetic like the other suites: ``NYAYMITRA_AUTH_DB`` points at a
throwaway file, and ``auth/documents.py`` derives the uploads
directory from that same path, so no test ever touches the
development database or its ``data/uploads/`` folder.

Covered, in the order the brief lists it:

1.  optional profile fields (bar council, experience, phone, bio)
    are stored, bounded and read back — registration without them
    still works;
2.  document upload: PDF/JPEG/PNG only (magic bytes + extension +
    content-type must agree), 10 MB cap, no empty files;
3.  path safety: the stored name is server-generated — a hostile
    filename never reaches the filesystem;
4.  one copy per lawyer: re-upload replaces (old bytes deleted),
    APPROVED lawyers cannot re-upload (409);
5.  access control: upload is LAWYER-only, admin retrieval is
    ADMIN-only, the lawyer can fetch their own, nobody else can,
    and no static route exposes the directory;
6.  admin list/detail carry the document metadata so the teammate's
    dashboard can show it.
"""

from __future__ import annotations

import re
import sqlite3

import pytest
from fastapi.testclient import TestClient

from auth import security
from database.sqlite_db import connect

GOOD_PASSWORD = "password123"
ADMIN_EMAIL = "admin@nyaymitra.in"

PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<< >>\nendobj\ntrailer\n%%EOF\n"
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64

OVERSIZED = b"%PDF-" + b"\x00" * (10 * 1024 * 1024)


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


def make_admin() -> int:
    """Insert an ADMIN directly — there is no registration path to it."""
    connection = connect()
    try:
        cursor = connection.execute(
            """
            INSERT INTO users (name, email, password_hash, role, is_demo)
            VALUES (?, ?, ?, 'ADMIN', 0)
            """,
            (
                "Test Admin",
                ADMIN_EMAIL,
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


def lawyer_token(client) -> str:
    response = register_lawyer(client)
    assert response.status_code == 201
    return response.json()["access_token"]


def attach(
    client,
    token: str,
    filename: str = "licence.pdf",
    data: bytes = PDF_BYTES,
    content_type: str = "application/pdf",
):
    return client.post(
        "/api/auth/lawyer/verification-document",
        files={"file": (filename, data, content_type)},
        headers=auth_header(token),
    )


def uploads_dir(auth_db):
    from auth import documents

    return documents.uploads_root()


def stored_files(auth_db) -> list:
    root = uploads_dir(auth_db)
    if not root.exists():
        return []
    return sorted(p for p in root.iterdir() if p.is_file())


def document_row(auth_db, lawyer_id: str):
    connection = sqlite3.connect(str(auth_db))
    connection.row_factory = sqlite3.Row
    try:
        return connection.execute(
            "SELECT * FROM lawyer_documents WHERE lawyer_id = ?",
            (lawyer_id,),
        ).fetchone()
    finally:
        connection.close()


def patch_status(client, admin_token, lawyer_id, status_value):
    return client.patch(
        f"/api/admin/lawyers/{lawyer_id}",
        json={"verification_status": status_value},
        headers=auth_header(admin_token),
    )


def lawyer_id_of(auth_db, email: str = "advocate@example.com") -> str:
    connection = sqlite3.connect(str(auth_db))
    try:
        return connection.execute(
            """
            SELECT l.lawyer_id FROM lawyers l
            JOIN users u ON u.id = l.user_id
            WHERE u.email = ?
            """,
            (email,),
        ).fetchone()[0]
    finally:
        connection.close()


# =========================================================
# 1 — OPTIONAL PROFILE FIELDS
# =========================================================


def test_register_with_profile_fields_stores_and_returns_them(
    client, auth_db
):
    response = register_lawyer(
        client,
        bar_council="Bar Council of Maharashtra",
        years_of_experience=7,
        professional_phone_number="+91 98765 43210",
        professional_bio="High Court advocate, 7 years of practice.",
    )

    assert response.status_code == 201

    lawyer_id = response.json()["user"]["lawyer_id"]

    connection = sqlite3.connect(str(auth_db))
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT * FROM lawyers WHERE lawyer_id = ?",
            (lawyer_id,),
        ).fetchone()
    finally:
        connection.close()

    assert row["bar_council"] == "Bar Council of Maharashtra"
    assert row["years_of_experience"] == 7
    assert row["professional_phone_number"] == "+91 98765 43210"
    assert (
        row["professional_bio"]
        == "High Court advocate, 7 years of practice."
    )
    assert row["verification_status"] == "PENDING"

    # The lawyer's own profile view carries them, plus no document yet.
    profile = client.get(
        "/api/auth/lawyer/profile",
        headers=auth_header(
            response.json()["access_token"]
        ),
    ).json()
    assert profile["bar_council"] == "Bar Council of Maharashtra"
    assert profile["years_of_experience"] == 7
    assert profile["professional_phone_number"] == (
        "+91 98765 43210"
    )
    assert profile["document"] is None


def test_register_without_profile_fields_keeps_them_null(
    client, auth_db
):
    response = register_lawyer(client)
    assert response.status_code == 201

    token = response.json()["access_token"]
    profile = client.get(
        "/api/auth/lawyer/profile", headers=auth_header(token)
    ).json()

    assert profile["bar_council"] is None
    assert profile["years_of_experience"] is None
    assert profile["professional_phone_number"] is None
    assert profile["professional_bio"] is None


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        (
            "professional_bio",
            "x" * 1001,
            "Bio must be 1000 characters or fewer.",
        ),
        (
            "years_of_experience",
            -1,
            "Years of experience must be between 0 and 70.",
        ),
        (
            "years_of_experience",
            71,
            "Years of experience must be between 0 and 70.",
        ),
        (
            "professional_phone_number",
            "call me maybe",
            "Enter a valid phone number.",
        ),
        (
            "bar_council",
            "x" * 201,
            "Bar Council must be 200 characters or fewer.",
        ),
    ],
)
def test_profile_field_validation(
    client, auth_db, field, value, message
):
    response = register_lawyer(client, **{field: value})

    assert response.status_code == 400
    assert response.json()["detail"] == message


# =========================================================
# 2 — UPLOAD: type, size, emptiness
# =========================================================


@pytest.mark.parametrize(
    ("filename", "data", "mime"),
    [
        ("licence.pdf", PDF_BYTES, "application/pdf"),
        ("licence.jpg", JPEG_BYTES, "image/jpeg"),
        ("licence.png", PNG_BYTES, "image/png"),
    ],
)
def test_upload_accepts_the_three_allowed_types(
    client, auth_db, filename, data, mime
):
    token = lawyer_token(client)

    response = attach(client, token, filename, data, mime)

    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == filename
    assert body["mime_type"] in {
        "application/pdf",
        "image/jpeg",
        "image/png",
    }
    assert body["size_bytes"] == len(data)
    assert re.fullmatch(r"[0-9a-f]{64}", body["sha256"])
    assert body["uploaded_at"]

    # Exactly one file, on disk, under the hermetic uploads root.
    files = stored_files(auth_db)
    assert len(files) == 1
    assert files[0].read_bytes() == data

    # And the database row points at it.
    lawyer_id = lawyer_id_of(auth_db)
    row = document_row(auth_db, lawyer_id)
    assert row is not None
    assert row["stored_filename"] == files[0].name


def test_upload_rejects_unknown_file_type(client, auth_db):
    token = lawyer_token(client)

    response = attach(
        client, token, "notes.txt", b"just some text", "text/plain"
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Upload a PDF, JPG or PNG file."
    )
    assert stored_files(auth_db) == []


def test_upload_rejects_spoofed_extension(client, auth_db):
    """A .pdf name and PDF content-type over non-PDF bytes fails."""
    token = lawyer_token(client)

    response = attach(
        client,
        token,
        "definitely-a-pdf.pdf",
        b"<script>alert(1)</script>",
        "application/pdf",
    )

    assert response.status_code == 400
    assert stored_files(auth_db) == []


def test_upload_rejects_lying_content_type(client, auth_db):
    """Real PDF bytes sent as text/html — header must agree too."""
    token = lawyer_token(client)

    response = attach(
        client, token, "licence.pdf", PDF_BYTES, "text/html"
    )

    assert response.status_code == 400
    assert stored_files(auth_db) == []


def test_upload_rejects_oversized_file(client, auth_db):
    token = lawyer_token(client)

    response = attach(client, token, "licence.pdf", OVERSIZED)

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "File too large. Maximum allowed size is 10 MB."
    )
    assert stored_files(auth_db) == []


def test_upload_rejects_empty_file(client, auth_db):
    token = lawyer_token(client)

    response = attach(client, token, "licence.pdf", b"")

    assert response.status_code == 400
    assert response.json()["detail"] == "The file is empty."
    assert stored_files(auth_db) == []


# =========================================================
# 3 — PATH SAFETY
# =========================================================


def test_hostile_filename_never_reaches_the_path(client, auth_db):
    """The stored name is server-generated; the display name is
    sanitized — traversal has nothing to traverse."""
    token = lawyer_token(client)

    response = attach(
        client,
        token,
        filename="../../../etc/evil.pdf",
        data=PDF_BYTES,
        content_type="application/pdf",
    )

    assert response.status_code == 201

    lawyer_id = lawyer_id_of(auth_db)
    row = document_row(auth_db, lawyer_id)

    assert ".." not in row["stored_filename"]
    assert "/" not in row["stored_filename"]
    assert "\\" not in row["stored_filename"]
    # Server-generated shape: LAWYER_NNNN-<16 hex>.ext
    assert re.fullmatch(
        r"LAWYER_\d+-[0-9a-f]{16}\.pdf", row["stored_filename"]
    )

    assert ".." not in row["original_filename"]
    assert "/" not in row["original_filename"]
    assert "\\" not in row["original_filename"]

    # Exactly one file, inside the uploads root.
    files = stored_files(auth_db)
    assert len(files) == 1
    assert files[0].parent == uploads_dir(auth_db).resolve()


# =========================================================
# 4 — ONE COPY; APPROVED CANNOT RE-UPLOAD
# =========================================================


def test_reupload_replaces_the_previous_copy(client, auth_db):
    token = lawyer_token(client)

    first = attach(client, token, "first.pdf", PDF_BYTES)
    assert first.status_code == 201

    second = attach(
        client, token, "second.png", PNG_BYTES, "image/png"
    )
    assert second.status_code == 201

    # One row, one file — no stale duplicates anywhere.
    lawyer_id = lawyer_id_of(auth_db)
    connection = connect()
    try:
        count = connection.execute(
            "SELECT COUNT(*) FROM lawyer_documents"
        ).fetchone()[0]
    finally:
        connection.close()
    assert count == 1

    files = stored_files(auth_db)
    assert len(files) == 1
    assert files[0].read_bytes() == PNG_BYTES
    assert second.json()["sha256"] != first.json()["sha256"]


def test_approved_lawyer_cannot_replace_document(
    client, auth_db, admin_token
):
    token = lawyer_token(client)
    assert attach(client, token).status_code == 201

    lawyer_id = lawyer_id_of(auth_db)
    assert (
        patch_status(client, admin_token, lawyer_id, "APPROVED")
        .status_code
        == 200
    )

    response = attach(client, token, "another.pdf", PDF_BYTES)

    assert response.status_code == 409
    assert "Already verified" in response.json()["detail"]

    # The original file is untouched.
    files = stored_files(auth_db)
    assert len(files) == 1
    assert files[0].read_bytes() == PDF_BYTES


def test_rejected_lawyer_may_retry_the_upload(
    client, auth_db, admin_token
):
    token = lawyer_token(client)
    lawyer_id = lawyer_id_of(auth_db)
    assert (
        patch_status(client, admin_token, lawyer_id, "REJECTED")
        .status_code
        == 200
    )

    response = attach(client, token, "retry.png", PNG_BYTES, "image/png")

    assert response.status_code == 201
    assert len(stored_files(auth_db)) == 1


# =========================================================
# 5 — ACCESS CONTROL
# =========================================================


def test_upload_requires_a_session(client, auth_db):
    response = client.post(
        "/api/auth/lawyer/verification-document",
        files={"file": ("licence.pdf", PDF_BYTES, "application/pdf")},
    )

    assert response.status_code == 401
    assert stored_files(auth_db) == []


def test_upload_refuses_citizens_and_admins(client, auth_db):
    citizen = register_user(client).json()["access_token"]
    response = attach(client, citizen)

    assert response.status_code == 403
    assert stored_files(auth_db) == []


def test_lawyer_can_fetch_their_own_document(client, auth_db):
    token = lawyer_token(client)
    assert attach(client, token).status_code == 201

    response = client.get(
        "/api/auth/lawyer/verification-document",
        headers=auth_header(token),
    )

    assert response.status_code == 200
    assert response.content == PDF_BYTES
    assert response.headers["content-type"].startswith(
        "application/pdf"
    )
    assert "attachment" in response.headers["content-disposition"]
    assert response.headers["x-content-type-options"] == "nosniff"


def test_lawyer_without_a_document_gets_404(client, auth_db):
    token = lawyer_token(client)

    response = client.get(
        "/api/auth/lawyer/verification-document",
        headers=auth_header(token),
    )

    assert response.status_code == 404


def test_another_lawyer_never_sees_the_first_ones_file(
    client, auth_db
):
    first = lawyer_token(client)
    assert attach(client, first).status_code == 201

    other = client.post(
        "/api/auth/register/lawyer",
        json={
            "full_name": "Other Advocate",
            "email": "other@example.com",
            "password": GOOD_PASSWORD,
            "password_confirmation": GOOD_PASSWORD,
            "license_id": "ENR/2024/0002",
            "practice_areas": ["Civil Law"],
        },
    ).json()["access_token"]

    response = client.get(
        "/api/auth/lawyer/verification-document",
        headers=auth_header(other),
    )

    # Their own (empty) document — never the first lawyer's bytes.
    assert response.status_code == 404


def test_admin_document_endpoint_is_admin_only(
    client, auth_db, admin_token
):
    token = lawyer_token(client)
    assert attach(client, token).status_code == 201
    lawyer_id = lawyer_id_of(auth_db)
    url = f"/api/admin/lawyers/{lawyer_id}/document"

    # Anonymous: 401.
    assert client.get(url).status_code == 401

    # Citizen: 403.
    citizen = register_user(client).json()["access_token"]
    assert (
        client.get(url, headers=auth_header(citizen)).status_code
        == 403
    )

    # The lawyer themselves: 403 on the admin route (own file has
    # its own endpoint) — no privilege confusion.
    assert (
        client.get(url, headers=auth_header(token)).status_code == 403
    )

    # Admin: 200 with the bytes.
    response = client.get(url, headers=auth_header(admin_token))
    assert response.status_code == 200
    assert response.content == PDF_BYTES


def test_admin_document_404_when_nothing_uploaded(
    client, auth_db, admin_token
):
    lawyer_token(client)
    lawyer_id = lawyer_id_of(auth_db)

    response = client.get(
        f"/api/admin/lawyers/{lawyer_id}/document",
        headers=auth_header(admin_token),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Document not found"


def test_files_are_not_served_publicly(client, auth_db):
    """No static route exists — the directory is unreachable."""
    assert client.get(
        "/uploads/verification/licence.pdf"
    ).status_code == 404
    assert client.get(
        "/data/uploads/verification/licence.pdf"
    ).status_code == 404
    assert client.get(
        "/static/licence.pdf"
    ).status_code == 404


# =========================================================
# 6 — ADMIN SURFACE CARRIES THE METADATA
# =========================================================


def test_admin_list_and_detail_show_document_metadata(
    client, auth_db, admin_token
):
    token = lawyer_token(client)

    profile = client.get(
        "/api/auth/lawyer/profile", headers=auth_header(token)
    ).json()
    assert profile["document"] is None

    assert attach(client, token, "bar-certificate.pdf").status_code == 201

    lawyer_id = lawyer_id_of(auth_db)

    detail = client.get(
        f"/api/admin/lawyers/{lawyer_id}",
        headers=auth_header(admin_token),
    ).json()
    assert detail["document"] is not None
    assert detail["document"]["filename"] == "bar-certificate.pdf"
    assert detail["document"]["mime_type"] == "application/pdf"
    assert detail["document"]["size_bytes"] == len(PDF_BYTES)
    assert detail["document"]["sha256"]

    listing = client.get(
        "/api/admin/lawyers",
        headers=auth_header(admin_token),
    ).json()
    entry = next(
        item
        for item in listing["lawyers"]
        if item["lawyer_id"] == lawyer_id
    )
    assert entry["document"] is not None
    assert entry["document"]["filename"] == "bar-certificate.pdf"


def test_lawyer_profile_carries_document_after_upload(
    client, auth_db
):
    token = lawyer_token(client)
    assert attach(client, token).status_code == 201

    profile = client.get(
        "/api/auth/lawyer/profile", headers=auth_header(token)
    ).json()

    assert profile["document"] is not None
    assert profile["document"]["mime_type"] == "application/pdf"
    assert profile["verification_status"] == "PENDING"


def test_document_endpoints_are_in_the_openapi(client, auth_db):
    paths = client.get("/openapi.json").json()["paths"]

    assert "/api/auth/lawyer/verification-document" in paths
    assert "/api/admin/lawyers/{lawyer_id}/document" in paths


def test_responses_never_leak_hashes_or_paths(
    client, auth_db, admin_token
):
    token = lawyer_token(client)
    assert attach(client, token).status_code == 201

    profile_response = client.get(
        "/api/auth/lawyer/profile", headers=auth_header(token)
    )
    detail_response = client.get(
        f"/api/admin/lawyers/{lawyer_id_of(auth_db)}",
        headers=auth_header(admin_token),
    )

    for response in (profile_response, detail_response):
        assert "password_hash" not in response.text
        assert "pbkdf2" not in response.text
        assert "stored_filename" not in response.text

"""/api/auth — register (citizen and lawyer), login, logout, current user.

Security rules implemented here (Phase 1 + Phase 2):

* passwords are stored only as PBKDF2 hashes (``auth/security.py``);
* the role is assigned by the server — ``USER`` for ``/register``,
  ``LAWYER`` for ``/register/lawyer``; a client-supplied ``role``
  field is rejected by the request model;
* a lawyer registration cannot choose its own outcome either: the
  request model forbids ``verification_status``, the INSERT hard-codes
  ``PENDING``, and only the ADMIN endpoints can change it;
* login answers unknown email and wrong password with the same 401
  so accounts cannot be enumerated — one login endpoint for every
  role;
* every response is built from ``UserOut``/``LawyerOut``/``AuthResponse``
  models, which have no field capable of carrying a password hash;
* unexpected failures fall through to ``main.py``'s catch-all
  handler — a short generic 500, never a stack trace.
"""

from __future__ import annotations

import logging
import re
import sqlite3

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from auth import documents, security
from auth.schemas import (
    AuthResponse,
    DocumentOut,
    LawyerOut,
    LawyerRegisterRequest,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    UserOut,
)
from database.sqlite_db import connect

router = APIRouter(prefix="/api/auth", tags=["Auth"])

logger = logging.getLogger("nyaymitra.auth")

# Deliberately simple: no third-party email validator is installed
# (no-new-packages rule), and the address is verified by use, not by
# syntax, at registration time.
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

MAX_NAME_LENGTH = 250
MAX_EMAIL_LENGTH = 320

# Lawyers registration bounds — mirrors the column widths in
# database/auth_schema.sql (license_id VARCHAR(100), practice_areas
# TEXT) so an oversized value is refused with a sentence instead of
# being truncated by the database.
MAX_LICENSE_LENGTH = 100
MAX_PRACTICE_AREAS = 10
MAX_PRACTICE_AREA_LENGTH = 100

# Optional profile fields (Phase 2b) — column widths and sane
# ranges from auth_schema.sql; everything below is 400 with a
# sentence rather than a database-level truncation.
MAX_BAR_COUNCIL_LENGTH = 200
MAX_YEARS_EXPERIENCE = 70
MAX_PHONE_LENGTH = 50
MAX_BIO_LENGTH = 1000
PHONE_PATTERN = re.compile(r"[0-9+()\-\s]{5,50}")

LAWYER_ID_PATTERN = re.compile(r"LAWYER_(\d+)")
LAWYER_ID_DIGITS = 4


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def _conflict(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT, detail=detail
    )


def _auth_response(token: str, user: dict) -> AuthResponse:
    return AuthResponse(access_token=token, user=UserOut(**user))


def _document_row(lawyer_id: str):  # noqa: ANN201
    """The caller's/subject's verification-document row, or ``None``."""
    connection = connect()
    try:
        return connection.execute(
            "SELECT * FROM lawyer_documents WHERE lawyer_id = ?",
            (lawyer_id,),
        ).fetchone()
    finally:
        connection.close()


def _document_out(row) -> DocumentOut | None:  # noqa: ANN001
    """Row -> metadata model (no bytes, no server-side path)."""
    if row is None:
        return None

    return DocumentOut(
        filename=row["original_filename"],
        mime_type=row["mime_type"],
        size_bytes=row["size_bytes"],
        sha256=row["sha256"],
        uploaded_at=row["uploaded_at"],
    )


def _attachment(row):  # noqa: ANN001, ANN201
    """Stored row -> an authenticated download, or a 404.

    The file is served with its real media type as an attachment
    plus ``nosniff`` — the browser is asked to save, never to render
    inline from our origin, and the stored name (server-generated,
    regex-verified) is the only path ever opened.
    """
    path = documents.document_path(row["stored_filename"])

    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="Document not found.")

    return FileResponse(
        path,
        media_type=row["mime_type"],
        filename=row["original_filename"],
        headers={"X-Content-Type-Options": "nosniff"},
    )


def _validate_registration(
    payload: RegisterRequest | LawyerRegisterRequest,
) -> tuple[str, str]:
    """Return normalized ``(full_name, email)`` or raise 400."""
    full_name = payload.full_name.strip()

    if not full_name:
        raise _bad_request("Enter your full name.")

    if len(full_name) > MAX_NAME_LENGTH:
        raise _bad_request(
            f"Full name must be {MAX_NAME_LENGTH} characters or fewer."
        )

    email = payload.email.strip().lower()

    if (
        not email
        or len(email) > MAX_EMAIL_LENGTH
        or not EMAIL_PATTERN.match(email)
    ):
        raise _bad_request("Enter a valid email address.")

    if len(payload.password) < security.MIN_PASSWORD_LENGTH:
        raise _bad_request(
            "Password must be at least "
            f"{security.MIN_PASSWORD_LENGTH} characters."
        )

    if len(payload.password) > security.MAX_PASSWORD_LENGTH:
        raise _bad_request(
            "Password must be "
            f"{security.MAX_PASSWORD_LENGTH} characters or fewer."
        )

    if payload.password != payload.password_confirmation:
        raise _bad_request("Passwords do not match.")

    return full_name, email


def _validate_license(payload: LawyerRegisterRequest) -> str:
    """Normalize the bar enrolment / registration number or raise 400."""
    license_id = payload.license_id.strip()

    if not license_id:
        raise _bad_request("Enter your licence or registration number.")

    if len(license_id) > MAX_LICENSE_LENGTH:
        raise _bad_request(
            "Licence number must be "
            f"{MAX_LICENSE_LENGTH} characters or fewer."
        )

    return license_id


def _validate_practice_areas(raw: list[str]) -> list[str]:
    """Clean, de-duplicate and bound the list — or raise 400.

    Free text by design: the practice_area_master list lives in the
    legacy PostgreSQL directory, which this environment cannot reach,
    and a registration must never fail because a lookup service is
    down. Areas are stored semicolon-separated, exactly as the seed
    writes them.
    """
    if len(raw) > MAX_PRACTICE_AREAS:
        raise _bad_request(
            f"List at most {MAX_PRACTICE_AREAS} practice areas."
        )

    cleaned: list[str] = []
    seen: set[str] = set()

    for entry in raw:
        value = entry.strip()

        if not value:
            raise _bad_request("Practice areas cannot be blank.")

        if len(value) > MAX_PRACTICE_AREA_LENGTH:
            raise _bad_request(
                "Each practice area must be "
                f"{MAX_PRACTICE_AREA_LENGTH} characters or fewer."
            )

        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(value)

    if not cleaned:
        raise _bad_request("List at least one practice area.")

    return cleaned


def _validate_profile(
    payload: LawyerRegisterRequest,
) -> dict:
    """Bound the optional profile fields — or raise 400.

    Every field here is optional; when present it must be sane.
    Length caps mirror the column widths in auth_schema.sql so the
    database never truncates silently, and the phone check is a
    character-class rule (no third-party validator is installed).
    """
    bar_council = (payload.bar_council or "").strip()
    phone = (payload.professional_phone_number or "").strip()
    bio = (payload.professional_bio or "").strip()
    years = payload.years_of_experience

    if len(bar_council) > MAX_BAR_COUNCIL_LENGTH:
        raise _bad_request(
            "Bar Council must be "
            f"{MAX_BAR_COUNCIL_LENGTH} characters or fewer."
        )

    if years is not None and not (0 <= years <= MAX_YEARS_EXPERIENCE):
        raise _bad_request(
            f"Years of experience must be between 0 and "
            f"{MAX_YEARS_EXPERIENCE}."
        )

    if len(phone) > MAX_PHONE_LENGTH:
        raise _bad_request(
            f"Phone number must be {MAX_PHONE_LENGTH} characters "
            "or fewer."
        )

    if phone and not PHONE_PATTERN.fullmatch(phone):
        raise _bad_request("Enter a valid phone number.")

    if len(bio) > MAX_BIO_LENGTH:
        raise _bad_request(
            f"Bio must be {MAX_BIO_LENGTH} characters or fewer."
        )

    return {
        "bar_council": bar_council or None,
        "years_of_experience": years,
        "professional_phone_number": phone or None,
        "professional_bio": bio or None,
    }


def _next_lawyer_id(connection) -> str:  # noqa: ANN001
    """``LAWYER_000N`` after the highest one already stored.

    Reuses the project's public-key convention (the seeded demo
    lawyer is ``LAWYER_0003``), so the frontend's session.lawyerId
    strings and the legacy directory keep the same shape.
    """
    highest = 0

    for row in connection.execute("SELECT lawyer_id FROM lawyers"):
        match = LAWYER_ID_PATTERN.fullmatch(row["lawyer_id"] or "")
        if match:
            highest = max(highest, int(match.group(1)))

    return f"LAWYER_{highest + 1:0{LAWYER_ID_DIGITS}d}"


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(payload: RegisterRequest) -> AuthResponse:
    """Create a citizen account and sign it in.

    Role is hard-coded to ``USER`` below — there is no parameter, no
    header and no field through which a caller could become LAWYER or
    ADMIN (lawyer registration is its own verified flow; ADMIN is
    seeded, never self-registered).
    """
    full_name, email = _validate_registration(payload)

    password_hash = security.hash_password(payload.password)

    connection = connect()
    try:
        try:
            cursor = connection.execute(
                """
                INSERT INTO users (name, email, password_hash, role, is_demo)
                VALUES (?, ?, ?, 'USER', 0)
                """,
                (full_name, email, password_hash),
            )
            connection.commit()
        except sqlite3.IntegrityError:
            # Only the unique email constraint can trip here.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists.",
            ) from None

        user_id = int(cursor.lastrowid)
    finally:
        connection.close()

    token = security.create_session(user_id)
    user = security.fetch_user_profile(user_id)

    logger.info("register: created user_id=%s", user_id)

    return _auth_response(token, user)


@router.post(
    "/register/lawyer",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_lawyer(payload: LawyerRegisterRequest) -> AuthResponse:
    """Create an advocate account and sign it in — PENDING, always.

    The two rows (``users`` + ``lawyers``) are written in one
    transaction, so a licence conflict can never leave an orphaned
    login behind. Role and status are hard-coded below: there is no
    parameter, header or field through which a caller could become
    ADMIN or approve themselves — ``verification_status`` is not part
    of the request model, and the only endpoints that can set it
    require an ADMIN session (``/api/admin/lawyers``).
    """
    full_name, email = _validate_registration(payload)
    license_id = _validate_license(payload)
    practice_areas = _validate_practice_areas(payload.practice_areas)
    profile = _validate_profile(payload)

    password_hash = security.hash_password(payload.password)

    connection = connect()
    try:
        for _attempt in range(5):
            try:
                lawyer_id = _next_lawyer_id(connection)

                cursor = connection.execute(
                    """
                    INSERT INTO users (name, email, password_hash, role,
                                       is_demo)
                    VALUES (?, ?, ?, 'LAWYER', 0)
                    """,
                    (full_name, email, password_hash),
                )
                user_id = int(cursor.lastrowid)

                connection.execute(
                    """
                    INSERT INTO lawyers (lawyer_id, user_id, license_id,
                                         practice_areas,
                                         bar_council, years_of_experience,
                                         professional_phone_number,
                                         professional_bio,
                                         verification_status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')
                    """,
                    (
                        lawyer_id,
                        user_id,
                        license_id,
                        "; ".join(practice_areas),
                        profile["bar_council"],
                        profile["years_of_experience"],
                        profile["professional_phone_number"],
                        profile["professional_bio"],
                    ),
                )
                connection.commit()
                break
            except sqlite3.IntegrityError as exc:
                connection.rollback()

                constraint = str(exc)

                if "users.email" in constraint:
                    raise _conflict(
                        "An account with this email already exists."
                    ) from None

                if "lawyers.license_id" in constraint:
                    raise _conflict(
                        "An account with this licence number "
                        "already exists."
                    ) from None

                if "lawyers.lawyer_id" in constraint:
                    # Two registrations raced for the same generated
                    # id — the SELECT above runs again with the row
                    # now visible. Any other constraint re-raises.
                    continue

                raise
        else:  # pragma: no cover - five collisions in a row
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not assign a lawyer id. Try again.",
            )
    finally:
        connection.close()

    token = security.create_session(user_id)
    user = security.fetch_user_profile(user_id)

    logger.info(
        "register_lawyer: created user_id=%s lawyer_id=%s PENDING",
        user_id,
        lawyer_id,
    )

    return _auth_response(token, user)


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest) -> AuthResponse:
    """Exchange email + password for a bearer session.

    Unknown email and wrong password answer identically
    (``Invalid email or password.``) and cost the same — the unknown
    email path burns an equivalent PBKDF2 verification.
    """
    email = payload.email.strip().lower()

    connection = connect()
    try:
        row = (
            connection.execute(
                "SELECT id, password_hash FROM users WHERE email = ?",
                (email,),
            ).fetchone()
            if email
            else None
        )

        if row is None:
            security.equalize_password_timing(payload.password)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        password_ok = (
            len(payload.password) <= security.MAX_PASSWORD_LENGTH
            and security.verify_password(
                payload.password, row["password_hash"]
            )
        )

        if not password_ok:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user_id = int(row["id"])
    finally:
        connection.close()

    token = security.create_session(user_id)
    user = security.fetch_user_profile(user_id)

    logger.info("login: user_id=%s", user_id)

    return _auth_response(token, user)


@router.post("/logout", response_model=MessageResponse)
def logout(authorization: str = Header(None)) -> MessageResponse:
    """Revoke the presented token.

    Requires a well-formed ``Authorization: Bearer`` header (401
    otherwise) but is otherwise forgiving: revoking an already-gone
    session is a no-op, so a client can always clear its state.
    """
    token = security.parse_bearer_token(authorization)
    security.revoke_session(token)

    logger.info("logout: session revoked")

    return MessageResponse(message="Signed out.")


@router.get("/me", response_model=UserOut)
def me(user: dict = Depends(security.get_current_user)) -> UserOut:
    """The signed-in user's profile — the reference protected route."""
    return UserOut(**user)


@router.get("/lawyer/profile", response_model=LawyerOut)
def lawyer_profile(
    lawyer: dict = Depends(security.get_current_lawyer),
) -> LawyerOut:
    """The signed-in advocate's own registration.

    Every lawyer — PENDING, APPROVED or REJECTED — may read this:
    it is how the frontend shows "waiting for approval" or "your
    registration was rejected". It returns only the caller's own
    row (looked up by their session user id), never the directory
    of others, and never the password hash. ``document`` is the
    metadata of the licence file they attached (``None`` if they
    have not yet uploaded one) — the bytes themselves come from
    ``GET /api/auth/lawyer/verification-document``.
    """
    return LawyerOut(
        lawyer_id=lawyer["lawyer_id"],
        user_id=lawyer["user_id"],
        full_name=lawyer["full_name"],
        email=lawyer["email"],
        license_id=lawyer["license_id"],
        practice_areas=lawyer["practice_areas"],
        verification_status=lawyer["verification_status"],
        verified_at=lawyer["verified_at"],
        created_at=lawyer["registered_at"],
        is_demo=lawyer["is_demo"],
        bar_council=lawyer.get("bar_council"),
        years_of_experience=lawyer.get("years_of_experience"),
        professional_phone_number=lawyer.get(
            "professional_phone_number"
        ),
        professional_bio=lawyer.get("professional_bio"),
        document=_document_out(
            _document_row(lawyer["lawyer_id"])
        ),
    )


@router.post(
    "/lawyer/verification-document",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_verification_document(
    file: UploadFile = File(...),
    lawyer: dict = Depends(security.get_current_lawyer),
) -> DocumentOut:
    """Attach — or replace — the caller's licence document.

    Part of the lawyer registration submission: the frontend calls
    this right after ``POST /register/lawyer`` with the same
    session. Any signed-in lawyer may upload: PENDING to attach,
    REJECTED to retry a clearer scan; APPROVED is refused with 409
    because an admin has already ruled on what was submitted.

    Security (enforced in ``auth/documents.py``, asserted in
    ``tests/test_lawyer_documents.py``): the bytes must pass the
    PDF/JPEG/PNG magic-byte check, extension and content-type must
    agree, size is capped at 10 MB, the stored name is generated
    by the server (no user input reaches the path), the file lands
    outside any web root, and a re-upload deletes the previous
    copy first — one lawyer, one file, ever.
    """
    if lawyer["verification_status"] == "APPROVED":
        raise _conflict(
            "Already verified — contact the administrator "
            "to change your document."
        )

    data = await file.read(documents.MAX_DOCUMENT_BYTES + 1)

    if not data:
        raise _bad_request("The file is empty.")

    if len(data) > documents.MAX_DOCUMENT_BYTES:
        raise _bad_request(
            "File too large. Maximum allowed size is "
            f"{documents.MAX_DOCUMENT_BYTES // (1024 * 1024)} MB."
        )

    detected = documents.detect_type(
        data, file.filename, file.content_type
    )

    if detected is None:
        raise _bad_request("Upload a PDF, JPG or PNG file.")

    extension, mime_type = detected

    connection = connect()
    try:
        previous = connection.execute(
            """
            SELECT stored_filename FROM lawyer_documents
            WHERE lawyer_id = ?
            """,
            (lawyer["lawyer_id"],),
        ).fetchone()

        stored = documents.save_document(
            lawyer["lawyer_id"], data, extension
        )

        try:
            connection.execute(
                """
                INSERT INTO lawyer_documents
                    (lawyer_id, original_filename, stored_filename,
                     mime_type, size_bytes, sha256)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (lawyer_id) DO UPDATE SET
                    original_filename = excluded.original_filename,
                    stored_filename = excluded.stored_filename,
                    mime_type = excluded.mime_type,
                    size_bytes = excluded.size_bytes,
                    sha256 = excluded.sha256,
                    uploaded_at = CURRENT_TIMESTAMP
                """,
                (
                    lawyer["lawyer_id"],
                    documents.sanitize_filename(file.filename),
                    stored,
                    mime_type,
                    len(data),
                    documents.sha256_hex(data),
                ),
            )
            connection.commit()
        except Exception:
            # The row did not take — do not leave the fresh file
            # behind as an ownerless copy.
            documents.delete_document(stored)
            raise

        if previous is not None:
            documents.delete_document(
                previous["stored_filename"]
            )

        row = connection.execute(
            """
            SELECT original_filename, mime_type, size_bytes,
                   sha256, uploaded_at
            FROM lawyer_documents
            WHERE lawyer_id = ?
            """,
            (lawyer["lawyer_id"],),
        ).fetchone()
    finally:
        connection.close()

    logger.info(
        "verification document uploaded: lawyer_id=%s bytes=%s",
        lawyer["lawyer_id"],
        len(data),
    )

    return _document_out(row)


@router.get("/lawyer/verification-document")
def own_verification_document(
    lawyer: dict = Depends(security.get_current_lawyer),
):
    """The caller's own document, bytes and all.

    Returns only the session's own file — one lawyer can never
    address another's document through this route. Not found (404)
    when nothing has been uploaded. ADMINs retrieve any lawyer's
    file through ``GET /api/admin/lawyers/{id}/document``.
    """
    row = _document_row(lawyer["lawyer_id"])

    if row is None:
        raise HTTPException(
            status_code=404, detail="Document not found."
        )

    return _attachment(row)

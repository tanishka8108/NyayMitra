"""/api/admin — ADMIN-only lawyer verification (Phase 2).

The contract the Admin Dashboard (teammate-owned UI) is built
against — this module ships the API only, never the UI:

* ``GET  /api/admin/lawyers``            list registrations,
                                          ``?status=PENDING`` filter,
                                          same envelope shape as the
                                          existing ``GET /api/lawyers``;
* ``GET  /api/admin/lawyers/{lawyer_id}`` one registration in full
  (profile fields + document metadata);
* ``GET  /api/admin/lawyers/{lawyer_id}/document`` the uploaded
  licence/registration file — ADMIN-only, never public;
* ``PATCH /api/admin/lawyers/{lawyer_id}`` rule on it —
  ``{"verification_status": "APPROVED" | "REJECTED" | "PENDING"}``.

Self-approval is impossible by construction, not by convention:

1. every route requires ``require_role("ADMIN")`` — a lawyer token
   (their own or anyone's) is refused with 403 before the handler
   runs, so a lawyer can never reach the UPDATE that touches their
   own row;
2. the request model forbids any field besides the status itself;
3. there is no lawyer-facing route anywhere in the API that writes
   ``lawyers.verification_status`` — registration hard-codes
   PENDING and nothing else on the LAWYER side has an UPDATE.

The verification status vocabulary is exactly PENDING / APPROVED /
REJECTED (the CHECK constraint in database/auth_schema.sql), the
same values ``/api/auth/me`` and ``/api/auth/lawyer/profile``
return to the lawyer.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from auth import documents, security
from auth.schemas import (
    DocumentOut,
    LawyerListResponse,
    LawyerOut,
    VerificationStatus,
    VerificationUpdateRequest,
)
from database.sqlite_db import connect

router = APIRouter(prefix="/api/admin", tags=["Admin"])

logger = logging.getLogger("nyaymitra.admin")

# One message for "no such lawyer", the same words the legacy
# directory endpoint uses, so a dashboard error handler can treat
# both services alike.
NOT_FOUND = "Lawyer not found"
DOCUMENT_NOT_FOUND = "Document not found"

_LIST_SELECT = """
    SELECT l.lawyer_id, l.user_id, l.license_id, l.practice_areas,
           l.verification_status, l.verified_by, l.verified_at,
           l.created_at, u.name, u.email, u.is_demo,
           l.bar_council, l.years_of_experience,
           l.professional_phone_number, l.professional_bio,
           d.original_filename AS doc_filename,
           d.mime_type AS doc_mime_type,
           d.size_bytes AS doc_size_bytes,
           d.sha256 AS doc_sha256,
           d.uploaded_at AS doc_uploaded_at,
           d.stored_filename AS doc_stored_filename
    FROM lawyers l
    JOIN users u ON u.id = l.user_id
    LEFT JOIN lawyer_documents d ON d.lawyer_id = l.lawyer_id
"""


def _lawyer_out(row) -> LawyerOut:  # noqa: ANN001
    """A joined row -> the response model. Never the password hash:
    this projection does not select it and the model cannot hold it.
    """
    document = None
    if row["doc_filename"] is not None:
        document = DocumentOut(
            filename=row["doc_filename"],
            mime_type=row["doc_mime_type"],
            size_bytes=row["doc_size_bytes"],
            sha256=row["doc_sha256"],
            uploaded_at=row["doc_uploaded_at"],
        )

    return LawyerOut(
        lawyer_id=row["lawyer_id"],
        user_id=row["user_id"],
        full_name=row["name"],
        email=row["email"],
        license_id=row["license_id"],
        practice_areas=security.parse_practice_areas(
            row["practice_areas"]
        ),
        verification_status=row["verification_status"],
        verified_by=row["verified_by"],
        verified_at=row["verified_at"],
        created_at=row["created_at"],
        is_demo=bool(row["is_demo"]),
        bar_council=row["bar_council"],
        years_of_experience=row["years_of_experience"],
        professional_phone_number=row["professional_phone_number"],
        professional_bio=row["professional_bio"],
        document=document,
    )


def _fetch_lawyer(connection, lawyer_id: str):  # noqa: ANN001
    return connection.execute(
        _LIST_SELECT + " WHERE l.lawyer_id = ?",
        (lawyer_id,),
    ).fetchone()


@router.get("/lawyers", response_model=LawyerListResponse)
def list_lawyer_registrations(
    verification_status: VerificationStatus | None = Query(
        None,
        alias="status",
        description="Filter: PENDING, APPROVED or REJECTED.",
    ),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    admin: dict = Depends(security.require_role("ADMIN")),
) -> LawyerListResponse:
    """Every lawyer registration, newest first.

    Default (no ``status``) returns all three states so the
    dashboard can show counts; ``status=PENDING`` is the
    approvals queue. Envelope mirrors ``GET /api/lawyers``
    (count/total_count/page/limit/total_pages/lawyers) so both
    listings can render through the same client type.
    """
    where = ""
    params: list = []

    if verification_status is not None:
        where = " WHERE l.verification_status = ?"
        params.append(verification_status)

    connection = connect()
    try:
        total_count = connection.execute(
            "SELECT COUNT(*) FROM lawyers l" + where, params
        ).fetchone()[0]

        rows = connection.execute(
            _LIST_SELECT
            + where
            + " ORDER BY l.created_at DESC, l.lawyer_id DESC"
            + " LIMIT ? OFFSET ?",
            [*params, limit, (page - 1) * limit],
        ).fetchall()
    finally:
        connection.close()

    total_pages = (
        (total_count + limit - 1) // limit if total_count else 0
    )

    return LawyerListResponse(
        count=len(rows),
        total_count=total_count,
        page=page,
        limit=limit,
        total_pages=total_pages,
        lawyers=[_lawyer_out(row) for row in rows],
    )


@router.get(
    "/lawyers/{lawyer_id}",
    response_model=LawyerOut,
)
def get_lawyer_registration(
    lawyer_id: str,
    admin: dict = Depends(security.require_role("ADMIN")),
) -> LawyerOut:
    """One registration in full — bar details, practice areas and
    the current ruling, for the dashboard's detail view."""
    connection = connect()
    try:
        row = _fetch_lawyer(connection, lawyer_id.strip())
    finally:
        connection.close()

    if row is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)

    return _lawyer_out(row)


@router.get("/lawyers/{lawyer_id}/document")
def get_verification_document(
    lawyer_id: str,
    admin: dict = Depends(security.require_role("ADMIN")),
):
    """The uploaded licence document for one registration.

    ADMIN-only (the dependency refuses every other role with 403
    before this runs) — the directory is not served statically
    anywhere, so this endpoint plus the lawyer's own
    ``GET /api/auth/lawyer/verification-document`` are the *only*
    two ways bytes ever leave the server. Served as an attachment
    with ``nosniff``: saved to disk, never rendered from our origin.
    404 when the lawyer uploaded nothing or the file is gone.
    """
    connection = connect()
    try:
        row = connection.execute(
            """
            SELECT stored_filename, original_filename, mime_type
            FROM lawyer_documents
            WHERE lawyer_id = ?
            """,
            (lawyer_id.strip(),),
        ).fetchone()
    finally:
        connection.close()

    if row is None:
        raise HTTPException(
            status_code=404, detail=DOCUMENT_NOT_FOUND
        )

    path = documents.document_path(row["stored_filename"])

    if path is None or not path.is_file():
        raise HTTPException(
            status_code=404, detail=DOCUMENT_NOT_FOUND
        )

    logger.info(
        "verification document fetched: admin_id=%s lawyer_id=%s",
        admin["user_id"],
        lawyer_id.strip(),
    )

    return FileResponse(
        path,
        media_type=row["mime_type"],
        filename=row["original_filename"],
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.patch(
    "/lawyers/{lawyer_id}",
    response_model=LawyerOut,
)
def update_verification(
    lawyer_id: str,
    payload: VerificationUpdateRequest,
    admin: dict = Depends(security.require_role("ADMIN")),
) -> LawyerOut:
    """Approve, reject or reset one registration.

    ADMIN-only by the dependency above: any other signed-in role
    (including the lawyer whose registration this may be — the
    self-approval case) receives 403 before this function runs.
    ``verified_by``/``verified_at`` record which admin ruled and
    when; sending the status back to PENDING clears both, because
    "nobody has ruled" must read that way to every screen.
    """
    normalized = lawyer_id.strip()
    decision = payload.verification_status

    connection = connect()
    try:
        row = _fetch_lawyer(connection, normalized)

        if row is None:
            raise HTTPException(status_code=404, detail=NOT_FOUND)

        decided = decision != "PENDING"
        verified_at = (
            datetime.now(timezone.utc).isoformat() if decided else None
        )
        verified_by = admin["user_id"] if decided else None

        connection.execute(
            """
            UPDATE lawyers
            SET verification_status = ?,
                verified_by = ?,
                verified_at = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE lawyer_id = ?
            """,
            (decision, verified_by, verified_at, normalized),
        )
        connection.commit()

        updated = _fetch_lawyer(connection, normalized)
    finally:
        connection.close()

    logger.info(
        "verification: admin_id=%s lawyer_id=%s -> %s",
        admin["user_id"],
        normalized,
        decision,
    )

    return _lawyer_out(updated)

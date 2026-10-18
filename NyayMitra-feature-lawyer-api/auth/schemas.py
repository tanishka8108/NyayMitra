"""Request/response models for /api/auth and the admin verification API.

``extra="forbid"`` on the request models is deliberate: a client that
tries to smuggle its own ``role`` (for example ``"ADMIN"``) into the
registration payload gets a 422 instead of the field being quietly
ignored — and a lawyer registration that tries to send its own
``verification_status: "APPROVED"`` is refused the same way. The
server assigns the role and the status itself.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

# The three states the lawyers table's CHECK constraint allows.
# Nothing else can ever be stored or returned.
VerificationStatus = Literal["PENDING", "APPROVED", "REJECTED"]


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str
    email: str
    password: str
    password_confirmation: str


class LawyerRegisterRequest(BaseModel):
    """Citizen-facing advocate sign-up (Phase 2).

    The verification outcome is deliberately absent: registration
    always lands as PENDING and only an ADMIN can change it. The
    profile fields are optional; the licence document itself is
    attached by the follow-up multipart upload
    (POST /api/auth/lawyer/verification-document), which the
    registration page sends as part of the same submission.
    """

    model_config = ConfigDict(extra="forbid")

    full_name: str
    email: str
    password: str
    password_confirmation: str
    license_id: str
    practice_areas: list[str]
    bar_council: str | None = None
    years_of_experience: int | None = None
    professional_phone_number: str | None = None
    professional_bio: str | None = None


class VerificationUpdateRequest(BaseModel):
    """ADMIN's ruling on one registration — the only write path
    to ``lawyers.verification_status`` in the whole API."""

    model_config = ConfigDict(extra="forbid")

    verification_status: VerificationStatus


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str
    password: str


class UserOut(BaseModel):
    """Everything the client may know about an account.

    Never includes ``password_hash`` — the models simply have no such
    field, so a hash cannot leak through serialization.
    ``verification_status`` is set only for LAWYER accounts (PENDING /
    APPROVED / REJECTED) and stays ``None`` for USER and ADMIN.
    """

    user_id: int
    full_name: str
    email: str
    role: str
    is_demo: bool = False
    lawyer_id: str | None = None
    verification_status: VerificationStatus | None = None


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class DocumentOut(BaseModel):
    """Metadata of one verification document — never the bytes.

    The file itself is only reachable through an authenticated
    endpoint (own document or ADMIN), never through this model.
    """

    filename: str
    mime_type: str
    size_bytes: int
    sha256: str
    uploaded_at: str | None = None


class LawyerOut(BaseModel):
    """One lawyer registration as the admin (and the lawyer) sees it.

    Same no-hash guarantee as ``UserOut``: the model has no field that
    could carry one. ``practice_areas`` is returned as a real array
    regardless of how the column is stored. Profile fields are
    optional; ``document`` is ``None`` until one has been uploaded.
    """

    lawyer_id: str
    user_id: int
    full_name: str
    email: str
    license_id: str
    practice_areas: list[str]
    verification_status: VerificationStatus
    verified_by: int | None = None
    verified_at: str | None = None
    created_at: str | None = None
    is_demo: bool = False
    bar_council: str | None = None
    years_of_experience: int | None = None
    professional_phone_number: str | None = None
    professional_bio: str | None = None
    document: DocumentOut | None = None


class LawyerListResponse(BaseModel):
    """Envelope shaped like the existing ``GET /api/lawyers`` listing
    so the Admin Dashboard can render both with one type."""

    count: int
    total_count: int
    page: int
    limit: int
    total_pages: int
    lawyers: list[LawyerOut]


class MessageResponse(BaseModel):
    message: str

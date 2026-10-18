"""Request/response models for /api/chat — Phase 3.

Same rule as ``auth.schemas``: ``extra="forbid"`` on every request
model, so identity fields sent by the wrong role are refused with a
422 instead of being quietly ignored. The server always derives the
sender/participant from the session token — never from the payload.

The conversation and message tables predate this module (see
``database/auth_schema.sql``); these models only shape the JSON.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class ChatLawyerOut(BaseModel):
    """One APPROVED lawyer as the chat directory shows them.

    Only lawyers with ``verification_status = APPROVED`` ever reach
    this model — PENDING and REJECTED registrations are filtered out
    in the query. No email, no licence number, no phone: a citizen
    browsing for counsel needs a name and what they practise, not
    the advocate's personal contact details.
    """

    lawyer_id: str
    full_name: str
    practice_areas: list[str]
    years_of_experience: int | None = None
    professional_bio: str | None = None
    bar_council: str | None = None
    verification_status: Literal["APPROVED"] = "APPROVED"


class ChatLawyerListResponse(BaseModel):
    count: int
    lawyers: list[ChatLawyerOut]


class ConversationCreateRequest(BaseModel):
    """USER → open (or reuse) a thread with an APPROVED lawyer.

    ``user_id`` is deliberately absent: the caller's identity comes
    from their session, so a client cannot start a thread on
    somebody else's behalf.
    """

    model_config = ConfigDict(extra="forbid")

    lawyer_id: str
    case_cnr: str | None = None


class LawyerConversationCreateRequest(BaseModel):
    """Verified LAWYER → open (or reuse) a thread with a client.

    The symmetric counterpart: ``lawyer_id`` is absent for the same
    reason — the lawyer is identified by their session.
    """

    model_config = ConfigDict(extra="forbid")

    user_id: int
    case_cnr: str | None = None


class MessageCreateRequest(BaseModel):
    """One chat message. The sender is never in the payload."""

    model_config = ConfigDict(extra="forbid")

    message: str


class ChatMessageOut(BaseModel):
    id: int
    sender_id: int
    # "USER" or "LAWYER" — computed from which side of the thread the
    # sender sits on, never trusted from the client.
    sender_role: str
    message: str
    created_at: str


class ConversationOut(BaseModel):
    """One thread with both participants and its full history.

    Flat participant fields (``user_id``/``user_name``/
    ``lawyer_id``/``lawyer_name``) keep the shape identical for both
    sides of the conversation, so the frontend maps it once.
    """

    id: int
    user_id: int
    user_name: str
    lawyer_id: str
    lawyer_name: str
    case_cnr: str | None = None
    created_at: str
    updated_at: str
    messages: list[ChatMessageOut]


class ConversationListResponse(BaseModel):
    count: int
    conversations: list[ConversationOut]


class MessageListResponse(BaseModel):
    count: int
    messages: list[ChatMessageOut]

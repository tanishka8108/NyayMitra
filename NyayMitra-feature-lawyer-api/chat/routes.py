""" /api/chat — persistent user ↔ lawyer messaging (Phase 3).

The tables (``conversations`` / ``messages``) and the session system
both already existed in ``database/auth_schema.sql``; this module
adds only the HTTP surface. Design rules:

* **Identity always comes from the session.** Request models are
  ``extra="forbid"`` and carry no sender/participant identity for
  the role that is calling — a user payload cannot name a
  ``user_id``, a lawyer payload cannot name a ``lawyer_id``, and
  every row is written with the caller's own ids.
* **Only APPROVED lawyers are reachable.** The directory query
  filters ``verification_status = 'APPROVED'``, conversation creation
  refuses anything else (404 with a single non-enumerating message),
  and the lawyer-side routes sit behind ``require_verified_lawyer``,
  so PENDING/REJECTED registrations get 403 with their own status.
* **Participants only.** Conversation reads/writes load the row and
  compare it to the session's identity; anybody else — including a
  valid-but-different user or lawyer — gets 404, which leaks nothing
  about which ids exist.
* **No WebSockets** — plain HTTP polling-style requests, matching
  the existing project.

Routing summary (ADMIN/STAFF have no chat surface: 403):

    GET    /api/chat/lawyers                      any signed-in account
    GET    /api/chat/conversations                USER
    POST   /api/chat/conversations                USER   (get-or-create)
    GET    /api/chat/lawyer/conversations         verified LAWYER
    POST   /api/chat/lawyer/conversations         verified LAWYER (get-or-create)
    GET    /api/chat/conversations/{id}           participant
    GET    /api/chat/conversations/{id}/messages  participant
    POST   /api/chat/conversations/{id}/messages  participant
"""

from __future__ import annotations

import logging
import re
import sqlite3

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Response,
    status,
)

from auth import security
from chat.schemas import (
    ChatLawyerListResponse,
    ChatLawyerOut,
    ChatMessageOut,
    ConversationCreateRequest,
    ConversationListResponse,
    ConversationOut,
    LawyerConversationCreateRequest,
    MessageCreateRequest,
    MessageListResponse,
)
from database.sqlite_db import connect

router = APIRouter(prefix="/api/chat", tags=["Chat"])

logger = logging.getLogger("nyaymitra.chat")

# Message bounds: TEXT has no limit in SQLite, so the limit lives
# here — a 400 with a sentence instead of an unbounded row.
MAX_MESSAGE_LENGTH = 4000

# The project's CNR format, exactly as the cases service defines it
# (cases/routes.py rejects anything else): four letters followed by
# twelve digits, e.g. MHPU210000042026. Normalised to upper case.
CNR_PATTERN = re.compile(r"^[A-Z]{4}[0-9]{12}$")

# lawyers.lawyer_id is VARCHAR(20); refuse longer input outright.
MAX_LAWYER_ID_LENGTH = 20

CREATE_RETRIES = 5

NOT_FOUND = "Conversation not found."

# One message for "unknown lawyer", "pending lawyer" and "rejected
# lawyer" targets alike: a citizen must not be able to probe which
# licence ids exist or how far a registration got.
LAWYER_UNAVAILABLE = "Lawyer not found or not available for chat."


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def _conversation_not_found() -> HTTPException:
    return HTTPException(status_code=404, detail=NOT_FOUND)


# =========================================================
# IDENTITY / ACCESS
# =========================================================


def require_chat_participant(authorization: str = Header(None)) -> dict:
    """Signed-in USER or verified LAWYER — never ADMIN/STAFF.

    401 when signed out (``get_current_user``), 403 with the fixed
    message used everywhere else for other roles, and the lawyer's
    own PENDING/REJECTED status message via
    ``security.ensure_verified_lawyer`` — the same access rule the
    Phase 2 guard uses, so chat and the rest of the lawyer feature
    set can never disagree.
    """
    user = security.get_current_user(authorization)

    if user["role"] == "USER":
        return user

    if user["role"] == "LAWYER":
        lawyer = security.get_current_lawyer(authorization)
        return security.ensure_verified_lawyer(lawyer)

    raise HTTPException(
        status_code=403,
        detail="You do not have permission to perform this action.",
    )


def _authorize_participant(actor: dict, conversation) -> None:  # noqa: ANN001
    """404 unless the session's own identity sits on this thread.

    404 rather than 403 on purpose: 403 would confirm the id exists,
    which is exactly what an id-probing attacker wants to learn.
    """
    if actor["role"] == "USER":
        mine = conversation["user_id"] == actor["user_id"]
    else:  # LAWYER — dependency already proved verification
        mine = conversation["lawyer_id"] == actor["lawyer_id"]

    if not mine:
        raise _conversation_not_found()


# =========================================================
# VALIDATION
# =========================================================


def _validate_message(raw: str) -> str:
    body = (raw or "").strip()

    if not body:
        raise _bad_request("Message cannot be blank.")

    if len(body) > MAX_MESSAGE_LENGTH:
        raise _bad_request(
            f"Message must be {MAX_MESSAGE_LENGTH} characters "
            "or fewer."
        )

    return body


def _normalize_case_cnr(raw: str | None) -> str | None:
    """Optional case link — format-checked, never invented.

    My Cases stores CNRs (four letters + twelve digits, the exact
    format ``cases/routes.py`` enforces); anything else
    is refused with 400 rather than silently stored, and an empty
    value simply means "no case attached".
    """
    if raw is None:
        return None

    value = raw.strip().upper()

    if not value:
        return None

    if not CNR_PATTERN.fullmatch(value):
        raise _bad_request(
            "case_cnr must be a valid CNR: four letters "
            "followed by twelve digits."
        )

    return value


# =========================================================
# ROW HELPERS
# =========================================================

_CONVERSATION_SQL = """
SELECT c.id, c.user_id, c.lawyer_id, c.case_cnr, c.created_at,
       u.name  AS user_name,
       lu.name AS lawyer_name
FROM conversations c
JOIN users   u  ON u.id  = c.user_id
JOIN lawyers l  ON l.lawyer_id = c.lawyer_id
JOIN users   lu ON lu.id = l.user_id
"""


def _fetch_conversation(connection, conversation_id: int):  # noqa: ANN001, ANN201
    return connection.execute(
        _CONVERSATION_SQL + " WHERE c.id = ?",
        (conversation_id,),
    ).fetchone()


def _find_pair(connection, user_id: int, lawyer_id: str):  # noqa: ANN001, ANN201
    return connection.execute(
        _CONVERSATION_SQL + " WHERE c.user_id = ? AND c.lawyer_id = ?",
        (user_id, lawyer_id),
    ).fetchone()


def _message_out(row, conversation_user_id: int) -> ChatMessageOut:  # noqa: ANN001
    """Row -> model.

    ``sender_role`` is derived from which side of the thread the
    sender sits on — it is never stored, so it cannot be spoofed.
    """
    return ChatMessageOut(
        id=row["id"],
        sender_id=row["sender_id"],
        sender_role=(
            "USER"
            if row["sender_id"] == conversation_user_id
            else "LAWYER"
        ),
        message=row["message"],
        created_at=row["created_at"],
    )


def _load_messages(connection, conversation_id: int, conversation_user_id: int) -> list[ChatMessageOut]:  # noqa: ANN001
    rows = connection.execute(
        """
        SELECT id, sender_id, message, created_at
        FROM messages
        WHERE conversation_id = ?
        ORDER BY id ASC
        """,
        (conversation_id,),
    ).fetchall()

    return [_message_out(row, conversation_user_id) for row in rows]


def _conversation_out(connection, row) -> ConversationOut:  # noqa: ANN001
    messages = _load_messages(connection, row["id"], row["user_id"])

    return ConversationOut(
        id=row["id"],
        user_id=row["user_id"],
        user_name=row["user_name"],
        lawyer_id=row["lawyer_id"],
        lawyer_name=row["lawyer_name"],
        case_cnr=row["case_cnr"] or None,
        created_at=row["created_at"],
        updated_at=(
            messages[-1].created_at if messages else row["created_at"]
        ),
        messages=messages,
    )


# Newest activity first — a thread with a fresh reply rises above an
# untouched older one; ties fall back to creation order.
_ACTIVITY_ORDER = (
    "ORDER BY COALESCE("
    "(SELECT m.created_at FROM messages m"
    " WHERE m.conversation_id = c.id ORDER BY m.id DESC LIMIT 1),"
    " c.created_at) DESC, c.id DESC"
)


def _list_conversations(connection, where: str, params: tuple) -> ConversationListResponse:  # noqa: ANN001
    rows = connection.execute(
        _CONVERSATION_SQL + " WHERE " + where + _ACTIVITY_ORDER,
        params,
    ).fetchall()

    return ConversationListResponse(
        count=len(rows),
        conversations=[
            _conversation_out(connection, row) for row in rows
        ],
    )


# =========================================================
# DIRECTORY — APPROVED lawyers available for chat
# =========================================================


@router.get("/lawyers", response_model=ChatLawyerListResponse)
def list_available_lawyers(
    user: dict = Depends(security.get_current_user),
) -> ChatLawyerListResponse:
    """Every APPROVED lawyer, for the citizen's "Chat with Lawyer".

    Requires a session (401 otherwise) but is open to any role that
    has one — the data is the public half of an advocate's profile.
    PENDING and REJECTED registrations never appear: the WHERE
    clause is the single source of truth for "verified".
    """
    connection = connect()
    try:
        rows = connection.execute(
            """
            SELECT l.lawyer_id, u.name, l.practice_areas,
                   l.years_of_experience, l.professional_bio,
                   l.bar_council
            FROM lawyers l
            JOIN users u ON u.id = l.user_id
            WHERE l.verification_status = 'APPROVED'
            ORDER BY u.name COLLATE NOCASE, l.lawyer_id
            """,
        ).fetchall()
    finally:
        connection.close()

    return ChatLawyerListResponse(
        count=len(rows),
        lawyers=[
            ChatLawyerOut(
                lawyer_id=row["lawyer_id"],
                full_name=row["name"],
                practice_areas=security.parse_practice_areas(
                    row["practice_areas"]
                ),
                years_of_experience=row["years_of_experience"],
                professional_bio=row["professional_bio"],
                bar_council=row["bar_council"],
            )
            for row in rows
        ],
    )


# =========================================================
# USER SIDE
# =========================================================


def _get_or_create(
    connection,
    *,
    user_id: int,
    lawyer_id: str,
    case_cnr: str | None,
    response: Response,
) -> ConversationOut:
    """One thread per (citizen, lawyer) pair — never a duplicate.

    An existing pair returns 200 unchanged (the earlier ``case_cnr``
    wins; the request cannot rewrite history). A fresh insert is
    retried through the unique-index race exactly like lawyer
    registration does.
    """
    existing = _find_pair(connection, user_id, lawyer_id)

    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return _conversation_out(connection, existing)

    for _attempt in range(CREATE_RETRIES):
        try:
            connection.execute(
                """
                INSERT INTO conversations (user_id, lawyer_id, case_cnr)
                VALUES (?, ?, ?)
                """,
                (user_id, lawyer_id, case_cnr),
            )
            connection.commit()
            break
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            constraint = str(exc)

            if "conversations_pair_unique" in constraint:
                # Lost a race against a parallel request for the
                # same pair — reuse what it created.
                existing = _find_pair(connection, user_id, lawyer_id)
                if existing is not None:
                    response.status_code = status.HTTP_200_OK
                    return _conversation_out(connection, existing)

            if "FOREIGN KEY" in constraint:
                # The lawyer disappeared between check and insert.
                raise HTTPException(
                    status_code=404, detail=LAWYER_UNAVAILABLE
                ) from None

            raise
    else:  # pragma: no cover - five collisions in a row
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not open the conversation. Try again.",
        )

    created = _find_pair(connection, user_id, lawyer_id)

    if created is None:  # pragma: no cover - insert reported success
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not open the conversation. Try again.",
        )

    logger.info(
        "conversation opened: id=%s user_id=%s lawyer_id=%s",
        created["id"],
        user_id,
        lawyer_id,
    )

    return _conversation_out(connection, created)


@router.get("/conversations", response_model=ConversationListResponse)
def list_my_conversations(
    user: dict = Depends(security.require_role("USER")),
) -> ConversationListResponse:
    """The signed-in citizen's threads — only their own, by query.

    An ADMIN or LAWYER session receives 403 here; there is no
    parameter that could widen the filter.
    """
    connection = connect()
    try:
        return _list_conversations(
            connection, "c.user_id = ?", (user["user_id"],)
        )
    finally:
        connection.close()


@router.post(
    "/conversations",
    response_model=ConversationOut,
    status_code=status.HTTP_201_CREATED,
)
def start_conversation(
    payload: ConversationCreateRequest,
    response: Response,
    user: dict = Depends(security.require_role("USER")),
) -> ConversationOut:
    """Open — or reuse — the caller's thread with one lawyer.

    The lawyer must exist **and** be APPROVED: PENDING/REJECTED and
    unknown ids answer identically (404), so this endpoint cannot be
    used to enumerate registrations or read their status. The
    ``user_id`` written is always the session's own.
    """
    lawyer_id = (payload.lawyer_id or "").strip()

    if not lawyer_id or len(lawyer_id) > MAX_LAWYER_ID_LENGTH:
        raise _bad_request("Choose a lawyer to message.")

    case_cnr = _normalize_case_cnr(payload.case_cnr)

    connection = connect()
    try:
        lawyer = connection.execute(
            """
            SELECT lawyer_id, verification_status
            FROM lawyers
            WHERE lawyer_id = ?
            """,
            (lawyer_id,),
        ).fetchone()

        if (
            lawyer is None
            or lawyer["verification_status"] != "APPROVED"
        ):
            raise HTTPException(
                status_code=404, detail=LAWYER_UNAVAILABLE
            )

        return _get_or_create(
            connection,
            user_id=user["user_id"],
            lawyer_id=lawyer_id,
            case_cnr=case_cnr,
            response=response,
        )
    finally:
        connection.close()


# =========================================================
# LAWYER SIDE (verified only — the dependency proves it)
# =========================================================


@router.get(
    "/lawyer/conversations",
    response_model=ConversationListResponse,
)
def list_lawyer_conversations(
    lawyer: dict = Depends(security.require_verified_lawyer),
) -> ConversationListResponse:
    """Threads involving the signed-in advocate — only theirs.

    PENDING/REJECTED registrations never reach the query: the
    dependency answers 403 with their own status first.
    """
    connection = connect()
    try:
        return _list_conversations(
            connection, "c.lawyer_id = ?", (lawyer["lawyer_id"],)
        )
    finally:
        connection.close()


@router.post(
    "/lawyer/conversations",
    response_model=ConversationOut,
    status_code=status.HTTP_201_CREATED,
)
def start_lawyer_conversation(
    payload: LawyerConversationCreateRequest,
    response: Response,
    lawyer: dict = Depends(security.require_verified_lawyer),
) -> ConversationOut:
    """Open — or reuse — the advocate's thread with a client.

    Mirrors the citizen endpoint: the target must be a real USER
    account (404 otherwise) and the ``lawyer_id`` written is always
    the session's own, so a payload cannot shift the thread onto a
    colleague's caseload.
    """
    connection = connect()
    try:
        target = connection.execute(
            """
            SELECT id
            FROM users
            WHERE id = ? AND role = 'USER'
            """,
            (payload.user_id,),
        ).fetchone()

        if target is None:
            raise HTTPException(
                status_code=404, detail="Account not found."
            )

        return _get_or_create(
            connection,
            user_id=payload.user_id,
            lawyer_id=lawyer["lawyer_id"],
            case_cnr=_normalize_case_cnr(payload.case_cnr),
            response=response,
        )
    finally:
        connection.close()


# =========================================================
# THREAD READS / SENDS — participant only
# =========================================================


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationOut,
)
def get_conversation(
    conversation_id: int,
    actor: dict = Depends(require_chat_participant),
) -> ConversationOut:
    """One thread with its full history — participants only.

    Unknown id and somebody else's id answer identically (404).
    """
    connection = connect()
    try:
        row = _fetch_conversation(connection, conversation_id)

        if row is None:
            raise _conversation_not_found()

        _authorize_participant(actor, row)

        return _conversation_out(connection, row)
    finally:
        connection.close()


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=MessageListResponse,
)
def list_messages(
    conversation_id: int,
    actor: dict = Depends(require_chat_participant),
) -> MessageListResponse:
    """The ordered history of one thread — participants only."""
    connection = connect()
    try:
        row = _fetch_conversation(connection, conversation_id)

        if row is None:
            raise _conversation_not_found()

        _authorize_participant(actor, row)

        messages = _load_messages(
            connection, row["id"], row["user_id"]
        )

        return MessageListResponse(
            count=len(messages), messages=messages
        )
    finally:
        connection.close()


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=ChatMessageOut,
    status_code=status.HTTP_201_CREATED,
)
def send_message(
    conversation_id: int,
    payload: MessageCreateRequest,
    actor: dict = Depends(require_chat_participant),
) -> ChatMessageOut:
    """Append one message to a thread the caller belongs to.

    ``sender_id`` is taken from the session — no payload field can
    post as somebody else (the request model does not even carry a
    sender). Message bodies are validated for length and never
    written to the logs.
    """
    body = _validate_message(payload.message)

    connection = connect()
    try:
        row = _fetch_conversation(connection, conversation_id)

        if row is None:
            raise _conversation_not_found()

        _authorize_participant(actor, row)

        cursor = connection.execute(
            """
            INSERT INTO messages (conversation_id, sender_id, message)
            VALUES (?, ?, ?)
            """,
            (conversation_id, actor["user_id"], body),
        )
        connection.commit()

        message_id = int(cursor.lastrowid)

        stored = connection.execute(
            """
            SELECT id, sender_id, message, created_at
            FROM messages
            WHERE id = ?
            """,
            (message_id,),
        ).fetchone()
    finally:
        connection.close()

    logger.info(
        "message sent: conversation_id=%s message_id=%s sender_id=%s",
        conversation_id,
        message_id,
        actor["user_id"],
    )

    return _message_out(stored, row["user_id"])

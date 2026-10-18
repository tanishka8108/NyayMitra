"""Password hashing, opaque bearer sessions and role guards.

No third-party packages: PBKDF2-HMAC-SHA256 comes from ``hashlib``
and tokens from ``secrets``. The frontend never chooses a role — the
role lives only in the ``users`` row and is read back from the
session on every request.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Callable

from fastapi import Depends, Header, HTTPException

from database.sqlite_db import connect

logger = logging.getLogger("nyaymitra.auth")

# ---------------------------------------------------------
# Passwords
# ---------------------------------------------------------

ALGORITHM = "pbkdf2_sha256"

# OWASP recommendation for PBKDF2-HMAC-SHA256.
PBKDF2_ITERATIONS = 600_000

SALT_BYTES = 16

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128


def hash_password(password: str) -> str:
    """Return ``pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>``.

    A fresh random salt is drawn per call, so two users sharing a
    password never share a hash.
    """
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS,
    )
    return f"{ALGORITHM}${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time check of ``password`` against a stored hash."""
    try:
        algorithm, iterations, salt_hex, digest_hex = stored.split("$")
    except (ValueError, AttributeError):
        return False

    if algorithm != ALGORITHM:
        return False

    try:
        recomputed = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations),
        )
    except (ValueError, TypeError):
        return False

    return hmac.compare_digest(recomputed.hex(), digest_hex)


_dummy_hash: str | None = None


def equalize_password_timing(password: str) -> None:
    """Burn the same PBKDF2 work when the email does not exist.

    Without this, a login for an unknown email returns faster than a
    login for a known email with a wrong password, which lets an
    attacker enumerate registered addresses by timing.
    """
    global _dummy_hash

    if _dummy_hash is None:
        _dummy_hash = hash_password("nyaymitra-timing-equalizer")

    verify_password(password, _dummy_hash)


# ---------------------------------------------------------
# Sessions — opaque random bearer tokens
# ---------------------------------------------------------

SESSION_TTL_DAYS = 30


def _hash_token(token: str) -> str:
    """SHA-256 of a token — what gets stored. A leaked sessions table
    never contains a usable token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(user_id: int) -> str:
    """Issue a fresh bearer token for ``user_id`` and return it raw."""
    token = secrets.token_urlsafe(32)
    expires_at = (
        datetime.now(timezone.utc) + timedelta(days=SESSION_TTL_DAYS)
    ).isoformat()

    connection = connect()
    try:
        connection.execute(
            "INSERT INTO sessions (token_hash, user_id, expires_at)"
            " VALUES (?, ?, ?)",
            (_hash_token(token), user_id, expires_at),
        )
        connection.commit()
    finally:
        connection.close()

    return token


def revoke_session(token: str) -> None:
    """Delete the session behind ``token`` (logout). No-op if absent."""
    connection = connect()
    try:
        connection.execute(
            "DELETE FROM sessions WHERE token_hash = ?",
            (_hash_token(token),),
        )
        connection.commit()
    finally:
        connection.close()


def _is_expired(expires_at: str) -> bool:
    try:
        expires = datetime.fromisoformat(expires_at)
    except (ValueError, TypeError):
        return True

    if expires.tzinfo is None:
        # SQLite's CURRENT_TIMESTAMP renders naive UTC.
        expires = expires.replace(tzinfo=timezone.utc)

    return datetime.now(timezone.utc) >= expires


def _profile_from_row(row) -> dict | None:  # noqa: ANN001
    if row is None:
        return None

    return {
        "user_id": row["id"],
        "full_name": row["name"],
        "email": row["email"],
        "role": row["role"],
        "is_demo": bool(row["is_demo"]),
        "lawyer_id": row["lawyer_id"] if "lawyer_id" in row.keys() else None,
        "verification_status": (
            row["verification_status"]
            if "verification_status" in row.keys()
            else None
        ),
    }


def fetch_user_profile(user_id: int) -> dict | None:
    """Load a user's public profile (never the password hash)."""
    connection = connect()
    try:
        row = connection.execute(
            """
            SELECT u.id, u.name, u.email, u.role, u.is_demo,
                   l.lawyer_id AS lawyer_id,
                   l.verification_status AS verification_status
            FROM users u
            LEFT JOIN lawyers l ON l.user_id = u.id
            WHERE u.id = ?
            """,
            (user_id,),
        ).fetchone()
        return _profile_from_row(row)
    finally:
        connection.close()


def fetch_session_user(token: str) -> dict | None:
    """Resolve a raw token to the signed-in user's profile.

    Returns ``None`` for unknown or expired tokens (expired rows are
    cleaned up on the way out).
    """
    connection = connect()
    try:
        token_hash = _hash_token(token)

        row = connection.execute(
            """
            SELECT u.id, u.name, u.email, u.role, u.is_demo,
                   l.lawyer_id AS lawyer_id,
                   l.verification_status AS verification_status,
                   s.expires_at
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            LEFT JOIN lawyers l ON l.user_id = u.id
            WHERE s.token_hash = ?
            """,
            (token_hash,),
        ).fetchone()

        if row is None:
            return None

        if _is_expired(row["expires_at"]):
            connection.execute(
                "DELETE FROM sessions WHERE token_hash = ?",
                (token_hash,),
            )
            connection.commit()
            return None

        return _profile_from_row(row)
    finally:
        connection.close()


# ---------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------


def unauthorized(detail: str) -> HTTPException:
    """401 with the standard ``WWW-Authenticate`` challenge."""
    return HTTPException(
        status_code=401,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def parse_bearer_token(authorization: str | None) -> str:
    """Extract the token from an ``Authorization: Bearer`` header."""
    if not authorization:
        raise unauthorized(
            "Not authenticated. Please sign in to continue."
        )

    scheme, separator, token = authorization.partition(" ")

    if separator != " " or scheme.lower() != "bearer" or not token.strip():
        raise unauthorized(
            "Not authenticated. Please sign in to continue."
        )

    return token.strip()


def get_current_user(authorization: str = Header(None)) -> dict:
    """Authenticated request → the user's profile, or 401.

    The identity comes from the server-side session row, never from
    anything the client sent.
    """
    token = parse_bearer_token(authorization)

    user = fetch_session_user(token)

    if user is None:
        raise unauthorized(
            "Your session has expired. Please sign in again."
        )

    return user


def require_role(*roles: str) -> Callable[..., dict]:
    """Dependency factory: only the listed roles may call the route.

    401 when signed out, 403 with a fixed, information-free message
    otherwise. Example::

        @router.get("/admin-only",
                    dependencies=[Depends(require_role("ADMIN"))])
    """

    def dependency(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to perform this action.",
            )
        return user

    return dependency


# ---------------------------------------------------------
# Lawyer account + verification-state guards
# ---------------------------------------------------------


def parse_practice_areas(stored: str | None) -> list[str]:
    """The lawyers table's semicolon text -> a JSON-ready array."""
    if not stored:
        return []
    return [entry.strip() for entry in stored.split(";") if entry.strip()]


def get_current_lawyer(authorization: str = Header(None)) -> dict:
    """Signed-in LAWYER -> profile + their own registration row.

    401 when signed out, 403 when the signed-in account is not a
    LAWYER. Every field returned is the lawyer's own — this is the
    only place a registration is read back for the person it
    belongs to, and it never carries anyone else's data.
    """
    user = get_current_user(authorization)

    if user["role"] != "LAWYER":
        raise HTTPException(
            status_code=403,
            detail="You do not have permission to perform this action.",
        )

    connection = connect()
    try:
        row = connection.execute(
            """
            SELECT lawyer_id, license_id, practice_areas,
                   verification_status, verified_at, created_at,
                   bar_council, years_of_experience,
                   professional_phone_number, professional_bio
            FROM lawyers
            WHERE user_id = ?
            """,
            (user["user_id"],),
        ).fetchone()
    finally:
        connection.close()

    if row is None:
        # Role says LAWYER but no registration row exists — treat as
        # not permitted rather than trusting the half-profile.
        raise HTTPException(
            status_code=403,
            detail="You do not have permission to perform this action.",
        )

    return {
        **user,
        "lawyer_id": row["lawyer_id"],
        "license_id": row["license_id"],
        "practice_areas": parse_practice_areas(row["practice_areas"]),
        "verification_status": row["verification_status"],
        "verified_at": row["verified_at"],
        "registered_at": row["created_at"],
        "bar_council": row["bar_council"],
        "years_of_experience": row["years_of_experience"],
        "professional_phone_number": row["professional_phone_number"],
        "professional_bio": row["professional_bio"],
    }


def ensure_verified_lawyer(lawyer: dict) -> dict:
    """The verification gate itself: APPROVED passes, else 403.

    Factored out of ``require_verified_lawyer`` so callers that
    already resolved the lawyer (the chat routes, which branch on
    role first) apply the exact same rule and the exact same
    messages — one definition of "verified lawyer" for the whole
    API. PENDING and REJECTED are refused with a message about
    *their own* status — the lawyer already knows it, so nothing
    about anyone else leaks.
    """
    status = lawyer["verification_status"]

    if status == "APPROVED":
        return lawyer

    if status == "PENDING":
        raise HTTPException(
            status_code=403,
            detail="Your lawyer registration is pending approval.",
        )

    if status == "REJECTED":
        raise HTTPException(
            status_code=403,
            detail="Your lawyer registration has been rejected.",
        )

    raise HTTPException(
        status_code=403,
        detail="You do not have permission to perform this action.",
    )


def require_verified_lawyer(
    lawyer: dict = Depends(get_current_lawyer),
) -> dict:
    """Dependency factory result: only an APPROVED lawyer passes.

    This is the server-side access rule for every lawyer-only
    feature (chat, the directory): the checks and messages live in
    ``ensure_verified_lawyer``. Citizens and admins get the same
    fixed 403 as everywhere else — but note this dependency is
    reached only after ``get_current_lawyer`` has already answered
    403 for non-LAWYER roles.
    """
    return ensure_verified_lawyer(lawyer)

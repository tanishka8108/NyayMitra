"""Server-side My Cases — save, list and remove a shortlist by CNR.

Why this sits beside the browser store
--------------------------------------
``frontend/src/api/caseApi.ts`` keeps its copy in ``localStorage``
(``nyaymitra.cases.added.v1``) on purpose: those screens are
synchronous and render on the first pass with no request to wait for.
That copy belongs to one browser profile, though — it cannot survive a
new machine, a private window or a cleared profile. These routes hold
the same shortlist on the server so it survives a refresh, a restart and
a reinstall. Nothing here reads or rewrites the browser's rows; they stay
exactly where they are until the frontend chooses to read this endpoint.

What is stored
--------------
Only ``user_id`` and ``cnr_number``. The case record itself is never
copied: the provider's dataset stays the single source of truth, so a
corrected hearing date or a renamed party shows up on the next read
instead of being frozen into a stale duplicate. Listing joins the record
at read time and reports ``case: null`` when the provider cannot produce
one, rather than dropping the row or inventing a placeholder.

Ownership
---------
``user_id`` comes from ``auth.security.get_current_user`` — a server-side
session row, never a field of the request body. There is no parameter
through which one account can name another. A CNR the signed-in account
did not save answers 404 rather than 403, matching the reasoning used in
``chat/routes.py``: 403 would confirm the row exists, which is what an
id-probing attacker wants to learn.

Failure handling
----------------
Malformed CNR 400 · unknown CNR 404 · signed out 401 · unexpected
failure 500 with a short safe message — stack traces, connection strings
and raw records stay in the server log, as in ``cases/routes.py``.
"""

from __future__ import annotations

import logging
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from auth import security
from cases.cnr import validate_cnr
from cases.provider import (
    CaseNotFoundError,
    ProviderUnavailableError,
    get_provider,
)
from database.sqlite_db import connect

router = APIRouter(prefix="/api/saved-cases", tags=["Saved Cases"])

logger = logging.getLogger("nyaymitra.saved_cases")

MAX_SAVED_PER_USER = 200

NOT_SAVED = "This case is not in your saved list."


class SavedCaseCreateRequest(BaseModel):
    """The only body accepted: a CNR. No user id, no role, no record."""

    cnr_number: str = Field(..., min_length=1, max_length=64)


def _describe(provider) -> dict:  # noqa: ANN001 - provenance must not break a list
    try:
        return provider.describe()
    except Exception:  # noqa: BLE001
        return {"provider": "unknown", "available": False}


def _attach(cnr: str, provider) -> dict:  # noqa: ANN001
    """One saved CNR plus its record, or ``case: null`` if unavailable.

    A CNR that the provider no longer knows is still listed — the
    citizen did save it, and hiding it would be a silent deletion.
    """
    try:
        record = provider.get_case(cnr)
    except Exception:  # noqa: BLE001 - provenance must not break a list
        return {"cnr_number": cnr, "case": None}
    return {"cnr_number": cnr, "case": record}


def _rows_for(user_id: int) -> list[sqlite3.Row]:
    connection = connect()
    try:
        return connection.execute(
            "SELECT cnr_number, saved_at FROM saved_cases "
            "WHERE user_id = ? ORDER BY saved_at DESC, id DESC",
            (user_id,),
        ).fetchall()
    finally:
        connection.close()


@router.get("")
def list_saved_cases(user: dict = Depends(security.get_current_user)):
    """This account's saved matters, newest first.

    Empty list is 200 — an account that saved nothing is a normal
    answer, not an error, so the screen can show its own empty state.
    """
    user_id = user["user_id"]
    rows = _rows_for(user_id)

    try:
        provider = get_provider()
        data_source = _describe(provider)
        items = [_attach(row["cnr_number"], provider) for row in rows]
        provider_broken = False
    except ProviderUnavailableError as exc:
        # The shortlist itself is still readable: report the rows with
        # no record and say plainly that the case source is down.
        logger.warning("saved cases listed while provider down: %s", exc)
        data_source = {"provider": "unavailable", "available": False}
        items = [{"cnr_number": row["cnr_number"], "case": None} for row in rows]
        provider_broken = True

    for item, row in zip(items, rows):
        item["saved_at"] = row["saved_at"]

    logger.info(
        "saved cases listed user_id=%s count=%d provider_ok=%s",
        user_id,
        len(items),
        not provider_broken,
    )

    return {
        "success": True,
        "items": items,
        "total": len(items),
        "data_source": data_source,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def save_case(
    payload: SavedCaseCreateRequest,
    response: Response,
    user: dict = Depends(security.get_current_user),
):
    """Add one CNR to this account's list.

    Answers 201 on a first save and 200 with ``already_saved: true``
    when the account already has it — deliberately idempotent, which is
    the behaviour ``caseApi.saveCaseForUser`` documents, so a double
    tap or a retry can never grow the list. The duplicate is blocked
    twice over: this check and the UNIQUE (user_id, cnr_number) index
    in ``database/auth_schema.sql``.
    """
    try:
        cnr = validate_cnr(payload.cnr_number)
    except ValueError as exc:
        logger.info("save case rejected: malformed CNR")
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    user_id = user["user_id"]

    connection = connect()
    try:
        existing = connection.execute(
            "SELECT id FROM saved_cases WHERE user_id = ? AND cnr_number = ?",
            (user_id, cnr),
        ).fetchone()

        if existing is not None:
            row = connection.execute(
                "SELECT cnr_number, saved_at FROM saved_cases WHERE user_id = ? "
                "AND cnr_number = ?",
                (user_id, cnr),
            ).fetchone()
            # The route is declared 201; a repeat save is a 200, because
            # nothing was created this time.
            response.status_code = status.HTTP_200_OK
            logger.info("save case user_id=%s cnr=%s result=already_saved", user_id, cnr)
            return {
                "success": True,
                "already_saved": True,
                "item": {
                    "cnr_number": row["cnr_number"],
                    "saved_at": row["saved_at"],
                    "case": None,
                },
            }

        total = connection.execute(
            "SELECT COUNT(*) AS n FROM saved_cases WHERE user_id = ?",
            (user_id,),
        ).fetchone()["n"]

        if total >= MAX_SAVED_PER_USER:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"You can save up to {MAX_SAVED_PER_USER} cases. "
                    "Remove one before saving another."
                ),
            )

        connection.execute(
            "INSERT INTO saved_cases (user_id, cnr_number) VALUES (?, ?)",
            (user_id, cnr),
        )
        connection.commit()
        row = connection.execute(
            "SELECT cnr_number, saved_at FROM saved_cases WHERE user_id = ? "
            "AND cnr_number = ?",
            (user_id, cnr),
        ).fetchone()
        # Read the values out now: the connection closes in the finally
        # block below, and a sqlite3.Row must not be touched afterwards.
        saved_cnr = row["cnr_number"]
        saved_at = row["saved_at"]
    except sqlite3.IntegrityError:
        # Lost the race against the UNIQUE index — the row exists, which
        # is the outcome the caller asked for.
        response.status_code = status.HTTP_200_OK
        logger.info("save case user_id=%s cnr=%s race=already_saved", user_id, cnr)
        return {
            "success": True,
            "already_saved": True,
            "item": {"cnr_number": cnr, "saved_at": None, "case": None},
        }
    except sqlite3.Error as exc:
        logger.warning("save case failed: %s", exc)
        raise HTTPException(
            status_code=500, detail="Your saved list could not be updated."
        ) from exc
    finally:
        connection.close()

    # The CNR must name a case this service can actually read: saving a
    # number that resolves to nothing would give the screen a card with
    # no facts behind it.
    try:
        provider = get_provider()
        provider.get_case(cnr)
    except CaseNotFoundError:
        _delete_row(user_id, cnr)
        logger.info("save case user_id=%s cnr=%s result=unknown_cnr", user_id, cnr)
        raise HTTPException(
            status_code=404,
            detail=(
                f"No case with CNR {cnr} is present in the data this "
                "service can read. Check the number, or use the official "
                "eCourts site for a live lookup."
            ),
        ) from None
    except Exception as exc:  # noqa: BLE001 - provider trouble, not caller error
        # Provider trouble must not silently discard a save the caller
        # asked for; keep the row and say the source is unavailable.
        logger.warning("save case kept while provider unavailable: %s", exc)

    logger.info("save case user_id=%s cnr=%s result=created", user_id, cnr)

    return {
        "success": True,
        "already_saved": False,
        "item": {
            "cnr_number": saved_cnr,
            "saved_at": saved_at,
            "case": None,
        },
    }


def _delete_row(user_id: int, cnr: str) -> bool:
    connection = connect()
    try:
        cursor = connection.execute(
            "DELETE FROM saved_cases WHERE user_id = ? AND cnr_number = ?",
            (user_id, cnr),
        )
        connection.commit()
        return cursor.rowcount > 0
    finally:
        connection.close()


@router.delete("/{cnr}")
def remove_saved_case(
    cnr: str,
    user: dict = Depends(security.get_current_user),
):
    """Drop one CNR from this account's list.

    200 when it was there, 404 when it was not — including when it
    belongs to somebody else, so the answer never differs between
    "nobody saved this" and "you saved that but I will not say".
    """
    try:
        cleaned = validate_cnr(cnr)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    user_id = user["user_id"]

    try:
        removed = _delete_row(user_id, cleaned)
    except sqlite3.Error as exc:
        logger.warning("remove saved case failed: %s", exc)
        raise HTTPException(
            status_code=500, detail="Your saved list could not be updated."
        ) from exc

    if not removed:
        logger.info("remove saved case user_id=%s cnr=%s result=not_found", user_id, cleaned)
        raise HTTPException(status_code=404, detail=NOT_SAVED)

    logger.info("remove saved case user_id=%s cnr=%s result=removed", user_id, cleaned)
    return {"success": True, "removed": True, "cnr_number": cleaned}

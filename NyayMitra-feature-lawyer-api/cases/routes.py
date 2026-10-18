"""My Cases endpoints.

One lookup route (``GET /api/cases/cnr/{cnr}``) and one browsable list
(``GET /api/cases``), both served through the provider abstraction in
``cases.provider``.

Every failure is translated into an HTTP status with a message that is
safe to show a citizen: a malformed CNR is a 400 that says what a CNR
looks like, an unknown CNR is a 404 naming only that CNR, and anything
unexpected becomes a 500 with no traceback and no query — stack traces,
connection strings and raw records stay in the server log.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from .cnr import validate_cnr
from .provider import (
    CaseDataError,
    CaseNotFoundError,
    ProviderUnavailableError,
    get_provider,
)
from .report_pdf import build_case_summary_pdf

router = APIRouter(prefix="/api/cases", tags=["Cases"])

logger = logging.getLogger("nyaymitra.cases")


def _describe(provider):
    """Provider provenance attached to every successful response."""
    try:
        return provider.describe()
    except Exception:  # noqa: BLE001 - provenance must not break a lookup
        return {"provider": "unknown", "available": False}


def _unavailable(exc: ProviderUnavailableError) -> HTTPException:
    logger.warning("case provider unavailable: %s", exc)
    return HTTPException(status_code=503, detail=str(exc))


@router.get("")
def list_cases(
    q: str = Query("", description="Matches CNR, party, case type or court."),
    status: str = Query("", description="'pending' or 'disposed'."),
    state: str = Query("", description="Court state, partial match."),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    """Browse the records the selected provider can serve."""
    try:
        provider = get_provider()
        result = provider.list_cases(
            query=q, status=status, state=state, page=page, limit=limit
        )
    except ProviderUnavailableError as exc:
        raise _unavailable(exc) from exc
    except CaseDataError as exc:
        logger.warning("case listing failed: %s", exc)
        raise HTTPException(status_code=500, detail="The case list could not be read.") from exc

    logger.info(
        "case list query_chars=%d status=%s page=%d results=%d",
        len(q.strip()),
        status or "-",
        page,
        len(result.get("items", [])),
    )

    return {"success": True, **result, "data_source": _describe(provider)}


@router.get("/cnr/{cnr}")
def get_case_by_cnr(cnr: str):
    """One case, in full: status, parties, court, next hearing, timeline
    and any orders recorded against it."""
    try:
        cleaned = validate_cnr(cnr)
    except ValueError as exc:
        logger.info("case lookup rejected: malformed CNR")
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        provider = get_provider()
    except ProviderUnavailableError as exc:
        raise _unavailable(exc) from exc

    try:
        record = provider.get_case(cleaned)
    except CaseNotFoundError:
        logger.info("case lookup cnr=%s result=not_found", cleaned)
        raise HTTPException(
            status_code=404,
            detail=(
                f"No case with CNR {cleaned} is present in the data this "
                "service can read. Check the number, or use the official "
                "eCourts site for a live lookup."
            ),
        ) from None
    except ProviderUnavailableError as exc:
        raise _unavailable(exc) from exc
    except CaseDataError as exc:
        logger.warning("case lookup failed: %s", exc)
        raise HTTPException(
            status_code=500, detail="The case record could not be read."
        ) from exc

    logger.info(
        "case lookup cnr=%s result=found status=%s orders=%d timeline=%d",
        cleaned,
        record.get("case_status", "-"),
        len(record.get("orders") or []),
        len(record.get("case_history_timeline") or []),
    )

    return {
        "success": True,
        "case": record,
        "data_source": _describe(provider),
    }


@router.get("/meta")
def cases_meta():
    """What this endpoint can answer — provider, size, provenance."""
    try:
        provider = get_provider()
        description = _describe(provider)
    except ProviderUnavailableError as exc:
        raise _unavailable(exc) from exc

    return {"success": True, "data_source": description}


@router.get("/cnr/{cnr}/report", response_class=Response)
def download_case_summary(cnr: str):
    """Download a PDF summary of the case record available to this provider."""
    try:
        cleaned = validate_cnr(cnr)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        provider = get_provider()
        record = provider.get_case(cleaned)
    except CaseNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No case with CNR {cleaned} is present in the data this "
                "service can read. Check the number, or use the official "
                "eCourts site for a live lookup."
            ),
        ) from None
    except ProviderUnavailableError as exc:
        raise _unavailable(exc) from exc
    except CaseDataError as exc:
        logger.warning("case report lookup failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="The case record could not be read for the report.",
        ) from exc

    try:
        pdf_bytes = build_case_summary_pdf(record, _describe(provider))
    except Exception as exc:
        logger.exception("case PDF generation failed")
        raise HTTPException(
            status_code=500,
            detail="The case summary PDF could not be generated.",
        ) from exc

    logger.info("case PDF generated cnr=%s", cleaned)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="NyayMitra-Case-Summary-{cleaned}.pdf"'
            ),
            "Cache-Control": "no-store",
        },
    )

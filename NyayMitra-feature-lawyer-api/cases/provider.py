"""Case data providers.

My Cases reads case records through this module instead of talking to a
particular database, so that where the data comes from is one decision
rather than a property of every route.

Two implementations live behind one interface:

``DevelopmentCaseProvider``
    Reads the offline development dataset that ships with this repo
    (``cases/data/development_cases.jsonl``) — a normalised copy of case
    records captured manually from the eCourts site by a team member.
    It is development / test / reference data only. It is *not* a live
    eCourts connection, it never has been, and responses say so.

``AuthorizedExternalCaseProvider``
    The seam where a real, authorised source (a database the project is
    entitled to read, or an official API with credentials) plugs in.
    Nothing is wired to it yet: until credentials exist it refuses to
    answer rather than inventing a case.

Select the provider with ``CASE_DATA_PROVIDER`` (``development`` by
default, ``external`` for the authorised source). The development
provider reads ``cases/data/development_cases.jsonl`` unless
``CASE_DATASET_PATH`` points at another file in the same shape.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .cnr import validate_cnr
from .timeline import build_timeline, sort_history

DATA_DIR = Path(__file__).resolve().parent / "data"
DEFAULT_DATASET = DATA_DIR / "development_cases.jsonl"

DEVELOPMENT_DISCLAIMER = (
    "Development dataset: offline case records captured manually from "
    "the eCourts site for building and testing My Cases. These are not "
    "live eCourts data and the record may be out of date."
)

EMPTY_VALUE = ""


class CaseDataError(Exception):
    """Base class for provider failures with a caller-safe message."""


class CaseNotFoundError(CaseDataError):
    """No record exists for the requested CNR."""


class ProviderUnavailableError(CaseDataError):
    """The selected provider cannot answer right now."""


def _parse_date(value: Any) -> date | None:
    """Read the ``YYYY-MM-DD`` dates the dataset uses, tolerating blanks."""
    if not value or not isinstance(value, str):
        return None

    text = value.strip()

    if not text:
        return None

    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text[:10] if fmt == "%Y-%m-%d" else text, fmt).date()
        except ValueError:
            continue

    return None


def _days_between(earlier: date | None, later: date | None) -> int:
    if earlier is None or later is None:
        return 0

    return max(0, (later - earlier).days)


def _enrich_record(record: dict[str, Any]) -> dict[str, Any]:
    """Per-request enrichment: counts, ordering, timeline.

    Three things cannot be written into the dataset file:

    * the metrics depend on *today*, so they are computed on read and a
      record does not go stale the day after it is written;
    * the capture stores its history newest-first, so ordering is fixed
      once here rather than in every screen that reads it;
    * the timeline mixes filing, registration, hearings, orders and the
      next listing into one chronological list (``cases.timeline``).
    """
    today = date.today()

    timeline = record.get("case_history_timeline") or []
    respondents = record.get("respondents_list") or []

    filing = _parse_date(record.get("filing_date"))

    latest_hearing: date | None = None
    for entry in timeline:
        for key in ("hearing_date", "business_on_date"):
            parsed = _parse_date(entry.get(key))
            if parsed and (latest_hearing is None or parsed > latest_hearing):
                latest_hearing = parsed

    stage_start = latest_hearing or filing

    enriched = sort_history(record)
    enriched["calculated_metrics"] = {
        "respondent_count": len(respondents),
        "total_case_age_days": _days_between(filing, today),
        "total_hearings_scheduled": len(timeline),
        "current_stage_duration_days": _days_between(stage_start, today),
    }
    enriched["timeline"] = build_timeline(enriched)

    return enriched


class CaseDataProvider:
    """Interface every case source implements."""

    def get_case(self, cnr: str) -> dict[str, Any]:
        raise NotImplementedError

    def list_cases(
        self,
        *,
        query: str = "",
        status: str = "",
        state: str = "",
        page: int = 1,
        limit: int = 20,
    ) -> dict[str, Any]:
        raise NotImplementedError

    def describe(self) -> dict[str, Any]:
        raise NotImplementedError


class DevelopmentCaseProvider(CaseDataProvider):
    """Offline dataset provider — the default, and the only one with data.

    The whole file is read once on first use and indexed by CNR; the
    dataset is a megabyte of JSON, so holding it costs less than
    re-reading it per request. Rebuild it from the raw captures with
    ``python -m cases.build_dev_dataset``.
    """

    def __init__(self, dataset_path: Path | str | None = None) -> None:
        self.dataset_path = Path(dataset_path or DEFAULT_DATASET)
        self._records: dict[str, dict[str, Any]] | None = None
        self._order: list[str] = []
        self._lock = threading.Lock()

    def _load(self) -> dict[str, dict[str, Any]]:
        if self._records is not None:
            return self._records

        with self._lock:
            if self._records is not None:
                return self._records

            if not self.dataset_path.exists():
                raise ProviderUnavailableError(
                    "The development case dataset is missing. Rebuild it "
                    "with `python -m cases.build_dev_dataset`."
                )

            records: dict[str, dict[str, Any]] = {}

            with self.dataset_path.open(encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        # A malformed line is a broken build, not a reason
                        # to fail every lookup: skip it and serve the rest.
                        continue

                    cnr = normalize_stored_cnr(record)
                    if cnr:
                        records[cnr] = record

            self._order = sorted(records)
            self._records = records

        return self._records

    def get_case(self, cnr: str) -> dict[str, Any]:
        cleaned = validate_cnr(cnr)

        records = self._load()
        record = records.get(cleaned)

        if record is None:
            raise CaseNotFoundError(cleaned)

        return _enrich_record(record)

    def list_cases(
        self,
        *,
        query: str = "",
        status: str = "",
        state: str = "",
        page: int = 1,
        limit: int = 20,
    ) -> dict[str, Any]:
        records = self._load()

        needle = (query or "").strip().lower()
        wanted_status = (status or "").strip().lower()
        wanted_state = (state or "").strip().lower()

        matches = []

        for cnr in self._order:
            record = records[cnr]

            if needle:
                haystack = " ".join(
                    [
                        record.get("cnr_number", ""),
                        record.get("case_type", ""),
                        record.get("petitioner_name", ""),
                        record.get("case_title", ""),
                        record.get("court_name", ""),
                        " ".join(record.get("respondents_list") or []),
                    ]
                ).lower()

                if needle not in haystack:
                    continue

            if wanted_status:
                case_status = (record.get("case_status") or "").lower()

                if wanted_status == "pending" and "pending" not in case_status:
                    continue

                if wanted_status == "disposed" and "disposed" not in case_status:
                    continue

            if wanted_state:
                if wanted_state not in (record.get("court_state") or "").lower():
                    continue

            matches.append(record)

        total = len(matches)
        page = max(1, page)
        limit = max(1, min(limit, 100))
        start = (page - 1) * limit
        window = matches[start : start + limit]

        return {
            "items": [_enrich_record(record) for record in window],
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": max(1, (total + limit - 1) // limit) if total else 0,
        }

    def describe(self) -> dict[str, Any]:
        try:
            records = self._load()
            available = True
            count = len(records)
        except CaseDataError:
            available = False
            count = 0

        return {
            "provider": "development",
            "label": "Offline development dataset",
            "available": available,
            "records": count,
            "live_ecourts_data": False,
            "disclaimer": DEVELOPMENT_DISCLAIMER,
        }


def normalize_stored_cnr(record: dict[str, Any]) -> str:
    raw = record.get("cnr_number") or ""

    try:
        return validate_cnr(raw)
    except ValueError:
        return ""


class AuthorizedExternalCaseProvider(CaseDataProvider):
    """Seam for an authorised, real case source.

    Deliberately not implemented: connecting to a live court database
    requires credentials and a right to use them that this project does
    not have yet. Until ``CASE_EXTERNAL_DSN`` (or whatever the
    authorised source turns out to be) is configured, this provider
    refuses every request with a 503-style error instead of returning
    anything it cannot stand behind — and it will never scrape
    eCourts, CAPTCHA included.
    """

    def __init__(self) -> None:
        self.dsn = os.environ.get("CASE_EXTERNAL_DSN", "").strip()

    @property
    def configured(self) -> bool:
        return bool(self.dsn)

    def _refuse(self) -> None:
        if not self.configured:
            raise ProviderUnavailableError(
                "No authorised external case source is configured. Set "
                "CASE_DATA_PROVIDER=development to use the offline "
                "development dataset."
            )

        raise ProviderUnavailableError(
            "The authorised external case source is configured but not "
            "implemented yet."
        )

    def get_case(self, cnr: str) -> dict[str, Any]:
        validate_cnr(cnr)
        self._refuse()

    def list_cases(self, **_: Any) -> dict[str, Any]:
        self._refuse()

    def describe(self) -> dict[str, Any]:
        return {
            "provider": "external",
            "label": "Authorised external case source",
            "available": self.configured,
            "records": 0,
            "live_ecourts_data": False,
            "disclaimer": (
                "An authorised external source has been selected but is "
                "not implemented, so this service cannot answer case "
                "requests."
            ),
        }


def build_provider() -> CaseDataProvider:
    """Create the provider named by ``CASE_DATA_PROVIDER``."""
    name = os.environ.get("CASE_DATA_PROVIDER", "development").strip().lower()

    if name in {"", "development", "dev", "file"}:
        # A different set of captures, without editing any code.
        dataset = os.environ.get("CASE_DATASET_PATH", "").strip()
        return DevelopmentCaseProvider(dataset or None)

    if name in {"external", "authorized", "authorised", "database"}:
        return AuthorizedExternalCaseProvider()

    raise ProviderUnavailableError(
        f"Unknown CASE_DATA_PROVIDER {name!r}. Use 'development' or 'external'."
    )


_provider: CaseDataProvider | None = None
_provider_lock = threading.Lock()


def get_provider() -> CaseDataProvider:
    """Process-wide provider instance (built on first use)."""
    global _provider

    if _provider is None:
        with _provider_lock:
            if _provider is None:
                _provider = build_provider()

    return _provider


def reset_provider() -> None:
    """Drop the cached provider. Used by tests that switch providers."""
    global _provider

    with _provider_lock:
        _provider = None

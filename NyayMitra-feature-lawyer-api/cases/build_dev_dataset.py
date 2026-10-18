"""Build ``cases/data/development_cases.jsonl`` from the raw captures.

Run from the API folder::

    python -m cases.build_dev_dataset

The raw material is the normalised case-status captures the team
collected manually from the eCourts site (a zip of them sits in the
repo root; it is extracted to ``dev_data/``). This script turns those
files into the one file ``DevelopmentCaseProvider`` reads: one JSON
record per line, keyed by CNR, with only the fields the API returns.

Why a build step instead of reading the captures at runtime:

* the raw captures carry page text, table dumps and every token the
  browser page contained — none of which the API should ever return;
* 132 files cover 109 CNRs, so duplicates have to be resolved once, in
  the open, rather than by whichever file a directory listing hits
  first;
* the provider then depends on one small, reviewable file.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parent
DEFAULT_SOURCE = REPO_ROOT / "dev_data"
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "data" / "development_cases.jsonl"

NOT_AVAILABLE = "Not available in the record."


def _clean(value: Any) -> str:
    if value is None:
        return ""

    text = str(value).strip()
    return text if text and text.lower() not in {"none", "null", "n/a"} else ""


def _first_party(parties: list[dict[str, Any]], wanted: str) -> dict[str, Any]:
    for party in parties:
        if (party.get("party_type") or "").upper() == wanted:
            return party
    return {}


def _party_names(parties: list[dict[str, Any]], wanted: str) -> list[str]:
    names = []
    for party in parties:
        if (party.get("party_type") or "").upper() == wanted:
            name = _clean(party.get("party_name"))
            if name:
                names.append(name)
    return names


def to_record(data: dict[str, Any]) -> dict[str, Any] | None:
    """Map one raw capture onto the API's case shape."""
    normalised = data.get("normalized_case") or {}
    case = normalised.get("case") or {}

    cnr = _clean(case.get("cnr_number"))
    if not cnr:
        return None

    parties = normalised.get("parties") or []
    petitioners = [p for p in parties if (p.get("party_type") or "").upper() == "PETITIONER"]
    acts = normalised.get("acts_and_sections") or []
    timeline = normalised.get("case_timeline") or []
    orders = normalised.get("case_orders") or []

    petitioner_party = petitioners[0] if petitioners else {}
    first_act = acts[0] if acts else {}

    case_status = _clean(case.get("case_status")) or "Unknown"
    stage = _clean(case.get("current_case_stage")) or case_status

    record: dict[str, Any] = {
        "cnr_number": cnr,
        "case_type": _clean(case.get("case_type")) or NOT_AVAILABLE,
        "case_title": _clean(case.get("case_title")),
        "filing_number": _clean(case.get("filing_number")) or NOT_AVAILABLE,
        "filing_date": _clean(case.get("filing_date")),
        "registration_number": _clean(case.get("registration_number")) or NOT_AVAILABLE,
        "registration_date": _clean(case.get("registration_date")),
        "first_hearing_date": _clean(case.get("first_hearing_date")),
        "next_hearing_date": _clean(case.get("next_hearing_date")),
        "disposal_date": _clean(case.get("disposal_date")),
        "business_on_date": _clean(case.get("business_on_date")),
        "case_status": case_status,
        "nature_of_disposal": _clean(case.get("nature_of_disposal")),
        "current_case_stage": stage,
        "presiding_judge": _clean(case.get("presiding_judge")) or NOT_AVAILABLE,
        "court_number_and_judge": _clean(case.get("court_number_and_judge")),
        "court_name": _clean(case.get("court_name")) or NOT_AVAILABLE,
        "court_state": _clean(case.get("court_state")) or NOT_AVAILABLE,
        "court_district": _clean(case.get("court_district")) or NOT_AVAILABLE,
        "court_complex": _clean(case.get("court_complex")),
        "petitioner_name": _clean(petitioner_party.get("party_name")) or NOT_AVAILABLE,
        "petitioner_advocate": _clean(petitioner_party.get("advocate_name")),
        "respondents_list": _party_names(parties, "RESPONDENT") or [NOT_AVAILABLE],
        # Every party as the capture names it — kept whole so the API and
        # the database loader read one list instead of one being derived
        # from the other and losing an advocate along the way.
        "parties": [
            {
                "party_type": _clean(party.get("party_type")).upper(),
                "party_name": _clean(party.get("party_name")),
                "advocate_name": _clean(party.get("advocate_name")) or None,
            }
            for party in parties
            if isinstance(party, dict) and _clean(party.get("party_name"))
        ],
        "applied_act": _clean(first_act.get("act")) or NOT_AVAILABLE,
        "applied_section": _clean(first_act.get("section")),
        "fir_number": _clean(case.get("fir_number")),
        "police_station": _clean(case.get("police_station")),
        "case_history_timeline": [
            {
                "judge_title": _clean(entry.get("judge")) or NOT_AVAILABLE,
                "business_on_date": _clean(entry.get("business_on_date")),
                "hearing_date": _clean(entry.get("hearing_date")),
                "purpose_of_hearing": _clean(entry.get("purpose_of_hearing"))
                or NOT_AVAILABLE,
            }
            for entry in timeline
            if isinstance(entry, dict)
        ],
        # `document_action` holds the site's displayPdf(...) javascript and
        # is deliberately dropped: nothing downstream needs it, and it is
        # not ours to re-serve.
        "orders": [
            {
                "order_type": _clean(order.get("order_type")) or "Order",
                "order_number": _clean(order.get("order_number")),
                "order_date": _clean(order.get("order_date")),
                "order_details": _clean(order.get("order_details")) or NOT_AVAILABLE,
                "order_section": _clean(order.get("source_order_section")),
            }
            for order in orders
            if isinstance(order, dict)
        ],
    }

    source = data.get("source") or {}
    record["record_source"] = {
        "source_name": _clean(source.get("source_name")),
        "source_module": _clean(source.get("source_module")),
        "data_status": _clean(source.get("data_status")),
        "fetched_at": _clean(source.get("fetched_at")),
    }

    quality = data.get("data_quality") or []
    if isinstance(quality, list) and quality:
        record["data_quality_flags"] = [
            _clean(item.get("severity", "")) + ": " + _clean(item.get("message", ""))
            for item in quality
            if isinstance(item, dict) and _clean(item.get("message"))
        ]

    return record


def completeness(record: dict[str, Any]) -> int:
    """How much a duplicate holds, so the fullest copy wins."""
    return (
        sum(1 for key, value in record.items() if value not in ("", [], None))
        + 3 * len(record.get("orders") or [])
        + len(record.get("case_history_timeline") or [])
    )


def collect(source: Path) -> dict[str, dict[str, Any]]:
    files = sorted(source.rglob("*_normalized.json"))

    if not files:
        raise SystemExit(
            f"No *_normalized.json captures found under {source}. "
            "Extract the case-data zip into that folder first."
        )

    records: dict[str, dict[str, Any]] = {}
    duplicates = 0

    for path in files:
        try:
            with path.open(encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"  skipping unreadable capture {path.name}: {exc}", file=sys.stderr)
            continue

        record = to_record(data)
        if record is None:
            continue

        cnr = record["cnr_number"]
        existing = records.get(cnr)

        if existing is None:
            records[cnr] = record
        else:
            duplicates += 1
            if completeness(record) > completeness(existing):
                records[cnr] = record

    print(f"Read {len(files)} capture file(s) -> {len(records)} distinct CNR(s)")
    if duplicates:
        print(f"Resolved {duplicates} duplicate capture(s), keeping the fullest record.")

    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    records = collect(args.source)

    if not records:
        print("No usable records — nothing written.", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)

    with args.output.open("w", encoding="utf-8") as handle:
        for cnr in sorted(records):
            handle.write(
                json.dumps(records[cnr], ensure_ascii=False, separators=(",", ":"))
                + "\n"
            )

    pending = sum(1 for r in records.values() if "pending" in r["case_status"].lower())
    disposed = sum(1 for r in records.values() if "disposed" in r["case_status"].lower())
    with_orders = sum(1 for r in records.values() if r["orders"])

    print(f"Wrote {len(records)} record(s) -> {args.output}")
    print(f"  pending={pending} disposed={disposed} with_orders={with_orders}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

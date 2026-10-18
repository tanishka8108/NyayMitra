"""Load ``cases/data/development_cases.jsonl`` into PostgreSQL.

The service ships with a file-backed provider, so nothing here runs by
itself. This is the loader for the day the project has a PostgreSQL
instance it is entitled to use::

    psql -U nyaymitra -d nyaymitra -f case_database.sql   # schema once
    python -m cases.load_dev_dataset                      # then the data
    CASE_DATA_PROVIDER=external uvicorn main:app           # read from it

It uses the same connection settings as every other query in this
service (``database.connection`` — no credentials of its own), writes
inside one transaction, and is idempotent: loading twice leaves the
same rows behind.

Rows written here are the project's development captures — manual
copies of eCourts pages kept for building My Cases. ``data_origin``
says so on every row, so a table full of them can never be mistaken
for a live feed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

DEFAULT_DATASET = Path(__file__).resolve().parent / "data" / "development_cases.jsonl"

NOT_AVAILABLE = "Not available in the record."

CASE_COLUMNS = (
    "cnr_number",
    "case_type",
    "case_title",
    "filing_number",
    "filing_date",
    "registration_number",
    "registration_date",
    "first_hearing_date",
    "next_hearing_date",
    "disposal_date",
    "business_on_date",
    "case_status",
    "nature_of_disposal",
    "current_case_stage",
    "presiding_judge",
    "court_number_and_judge",
    "court_name",
    "court_state",
    "court_district",
    "court_complex",
    "petitioner_name",
    "petitioner_advocate",
    "applied_act",
    "applied_section",
    "fir_number",
    "police_station",
)

DATE_COLUMNS = {
    "filing_date",
    "registration_date",
    "first_hearing_date",
    "next_hearing_date",
    "disposal_date",
    "business_on_date",
}

PLACEHOLDERS = ", ".join(["%s"] * len(CASE_COLUMNS))


def _date(value: Any) -> Any:
    """A date column value: ``None`` when the record has no usable date."""
    text = str(value or "").strip()

    if not text or text == NOT_AVAILABLE:
        return None

    return text


def _value(record: dict[str, Any], column: str) -> Any:
    """Turn a dataset value into something the column accepts.

    ``""`` and the dataset's ``Not available in the record.`` are not
    dates and not facts — they become NULL rather than a string the
    database would reject or a reader would mistake for data.
    """
    raw = record.get(column)

    if column in DATE_COLUMNS:
        return _date(raw)

    if raw is None:
        return None

    text = str(raw).strip()
    if not text or text == NOT_AVAILABLE:
        return None

    return text


def _replace_children(cursor, cnr: str, record: dict[str, Any]) -> tuple[int, int, int]:
    """Delete and rewrite this CNR's children — the load is idempotent."""
    cursor.execute("DELETE FROM case_orders WHERE cnr_number = %s", (cnr,))
    cursor.execute("DELETE FROM case_timeline WHERE cnr_number = %s", (cnr,))
    cursor.execute("DELETE FROM case_parties WHERE cnr_number = %s", (cnr,))

    parties = 0

    for position, party in enumerate(record.get("parties") or []):
        kind = str(party.get("party_type") or "").upper()
        name = str(party.get("party_name") or "").strip()

        if kind not in {"PETITIONER", "RESPONDENT"} or not name:
            continue

        advocate = str(party.get("advocate_name") or "").strip() or None

        cursor.execute(
            """
            INSERT INTO case_parties
                (cnr_number, party_type, party_name, advocate_name, position)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (cnr, kind, name, advocate, position),
        )
        parties += 1

    history = 0

    for position, row in enumerate(record.get("case_history_timeline") or []):
        if not isinstance(row, dict):
            continue

        cursor.execute(
            """
            INSERT INTO case_timeline
                (cnr_number, row_number, judge, business_on_date,
                 hearing_date, purpose_of_hearing)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                cnr,
                position + 1,
                str(row.get("judge_title") or "").strip() or None,
                _date(row.get("business_on_date")),
                _date(row.get("hearing_date")),
                str(row.get("purpose_of_hearing") or "").strip() or None,
            ),
        )
        history += 1

    orders = 0

    for order in record.get("orders") or []:
        if not isinstance(order, dict):
            continue

        cursor.execute(
            """
            INSERT INTO case_orders
                (cnr_number, order_type, order_number, order_date,
                 order_details, order_section)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                cnr,
                str(order.get("order_type") or "").strip() or None,
                str(order.get("order_number") or "").strip() or None,
                _value({"filing_date": order.get("order_date")}, "filing_date"),
                str(order.get("order_details") or "").strip() or None,
                str(order.get("order_section") or "").strip() or None,
            ),
        )
        orders += 1

    return parties, history, orders


def load(dataset: Path, dry_run: bool = False) -> int:
    from database.connection import get_db_connection

    if not dataset.exists():
        raise SystemExit(
            f"{dataset} not found. Build it with `python -m cases.build_dev_dataset`."
        )

    records = [
        json.loads(line)
        for line in dataset.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    if dry_run:
        print(f"dry run: {len(records)} record(s) would be loaded into {dataset}")
        return len(records)

    connection = get_db_connection()
    counts = {"parties": 0, "timeline": 0, "orders": 0}

    try:
        cursor = connection.cursor()
        try:
            for record in records:
                cnr = str(record.get("cnr_number") or "").strip()
                if not cnr:
                    continue

                values = [_value(record, column) for column in CASE_COLUMNS]

                cursor.execute(
                    f"""
                    INSERT INTO cases ({", ".join(CASE_COLUMNS)})
                    VALUES ({PLACEHOLDERS})
                    ON CONFLICT (cnr_number) DO UPDATE SET
                        {", ".join(
                            f"{column} = EXCLUDED.{column}"
                            for column in CASE_COLUMNS
                            if column != "cnr_number"
                        )},
                        record_source = EXCLUDED.record_source,
                        data_quality_flags = EXCLUDED.data_quality_flags,
                        data_origin = 'development_dataset'
                    """,
                    values
                    + [
                        json.dumps(record.get("record_source") or {}),
                        json.dumps(record.get("data_quality_flags") or []),
                    ],
                )

                parties, timeline, orders = _replace_children(cursor, cnr, record)
                counts["parties"] += parties
                counts["timeline"] += timeline
                counts["orders"] += orders

            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()
    finally:
        connection.close()

    print(
        f"Loaded {len(records)} case(s) — {counts['parties']} parties, "
        f"{counts['timeline']} history rows, {counts['orders']} orders."
    )
    return len(records)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count the records without writing anything.",
    )
    args = parser.parse_args(argv)

    load(args.dataset, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

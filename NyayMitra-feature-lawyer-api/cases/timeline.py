"""Chronological timeline for one case.

The case service stores a case's history the way a court website
prints it: newest entry first, hearing rows only. My Cases reads a
timeline the way a person reads a life story — oldest first, and with
the events that frame those hearings (when the matter was filed, when
it was registered, what the court has passed, when it is next listed)
in the same list.

Everything here is derived from values already on the record. Nothing
is inferred, no date is invented, and a row with no usable date is
kept and placed at the end rather than dropped, because a missing date
is a fact about the record and not a reason to lose the event.

Shape returned for each event::

    {
        "date": "2026-01-09",      # "" when the record has none
        "event": "Disposed",       # what happened
        "description": "Before …",  # where / who, when known
        "purpose": "Disposed",     # the court's own wording
        "stage": None | str        # stage, only where the record gives it
    }
"""

from __future__ import annotations

from typing import Any

NOT_AVAILABLE = "Not available in the record."


def _text(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip()


def _date_of(entry: dict[str, Any]) -> str:
    """The date a history row belongs on.

    ``business_on_date`` is the day the court listed the item; every
    captured row carries one. ``hearing_date`` is the day it was
    actually taken up, which is empty on the last sitting of many
    disposed matters — so it is only a fallback.
    """
    return _text(entry.get("business_on_date")) or _text(entry.get("hearing_date"))


def _event(
    *,
    date: str,
    event: str,
    description: str = "",
    purpose: str = "",
    stage: str | None = None,
) -> dict[str, Any]:
    return {
        "date": date,
        "event": event,
        "description": description,
        "purpose": purpose,
        "stage": stage,
    }


def _hearing_events(record: dict[str, Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []

    for entry in record.get("case_history_timeline") or []:
        if not isinstance(entry, dict):
            continue

        purpose = _text(entry.get("purpose_of_hearing"))
        judge = _text(entry.get("judge_title"))
        date = _date_of(entry)
        hearing = _text(entry.get("hearing_date"))

        description = f"Before {judge}." if judge and judge != NOT_AVAILABLE else ""

        # A row can carry two dates: the day it was listed and the day
        # it was heard. When they differ, say so rather than showing
        # one and hiding the other.
        if hearing and date and hearing != date:
            listed = f"{description} " if description else ""
            description = f"{listed}Taken up on {hearing}."

        events.append(
            _event(
                date=date,
                event=purpose or "Hearing held",
                description=description.strip(),
                purpose=purpose,
            )
        )

    return events


def _order_events(record: dict[str, Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []

    for order in record.get("orders") or []:
        if not isinstance(order, dict):
            continue

        details = _text(order.get("order_details"))
        section = _text(order.get("order_section"))
        number = _text(order.get("order_number"))
        kind = _text(order.get("order_type"))

        title = "Order passed"
        if kind:
            title = f"{kind} order passed" if kind != "Order" else "Order passed"
        if number:
            title = f"{title} — No. {number}"

        description = details if details and details != NOT_AVAILABLE else section

        events.append(
            _event(
                date=_text(order.get("order_date")),
                event=title,
                description=description,
                purpose=section,
            )
        )

    return events


def build_timeline(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Every event on the record, oldest first.

    ``case_history_timeline`` itself is left alone apart from being
    sorted into the same order — screens that count hearings read it,
    and a filing or a next-hearing date is not a hearing.
    """
    status = _text(record.get("case_status")).lower()

    events: list[dict[str, Any]] = []

    filing = _text(record.get("filing_date"))
    if filing:
        number = _text(record.get("filing_number"))
        events.append(
            _event(
                date=filing,
                event="Case filed",
                description=f"Filing number {number}." if number else "",
            )
        )

    registration = _text(record.get("registration_date"))
    if registration and registration != filing:
        number = _text(record.get("registration_number"))
        events.append(
            _event(
                date=registration,
                event="Case registered",
                description=f"Registration number {number}." if number else "",
            )
        )

    events.extend(_hearing_events(record))
    events.extend(_order_events(record))

    # The next hearing is only a future event while the matter is
    # still live. A disposed case that still carries a listing date
    # would otherwise show a date that can never arrive.
    next_hearing = _text(record.get("next_hearing_date"))
    if next_hearing and "disposed" not in status:
        stage = _text(record.get("current_case_stage"))
        judge = _text(record.get("presiding_judge"))

        description = f"Before {judge}." if judge and judge != NOT_AVAILABLE else ""
        if stage:
            listed = f"{description} " if description else ""
            description = f"{listed}Stage: {stage}."

        events.append(
            _event(
                date=next_hearing,
                event="Next hearing",
                description=description.strip(),
                stage=stage or None,
            )
        )

    return sort_timeline(events)


def sort_timeline(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Oldest first.

    * undated events sort last, in the order they were added;
    * duplicate dates keep their relative order (a filing and a
      registration on the same day stay filing-then-registration);
    * the sort is stable, so no event is ever silently discarded.
    """
    return sorted(
        events,
        key=lambda event: (1 if not event.get("date") else 0, event.get("date") or ""),
    )


def sort_history(record: dict[str, Any]) -> dict[str, Any]:
    """Return the record with its hearing rows in chronological order.

    The raw capture lists them newest first. Everything downstream —
    the dashboard, the delay analysis, the lawyer's caseload — reads
    them in the order they are given, so the ordering is fixed once
    here rather than in each screen.
    """
    rows = [
        row for row in (record.get("case_history_timeline") or [])
        if isinstance(row, dict)
    ]

    # A row with no date at all still belongs in the record: it goes
    # at the end rather than sorting to the top as an empty key would.
    with_dates = [row for row in rows if _date_of(row)]
    undated = [row for row in rows if not _date_of(row)]

    with_dates.sort(key=_date_of)  # stable: equal dates keep their order

    enriched = dict(record)
    enriched["case_history_timeline"] = with_dates + undated
    return enriched

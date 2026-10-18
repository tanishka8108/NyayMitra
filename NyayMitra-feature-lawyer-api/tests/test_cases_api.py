"""My Cases API — the checks the feature is judged by.

Run from the API folder::

    python -m pytest

These do not need a running server (``fastapi.testclient``) and never
touch the network: the development dataset on disk is the data source,
exactly as it is in production. ``tests/smoke_cases_api.py`` is the
companion check against a live ``uvicorn`` process.

What is covered, in the order the brief lists it:

1. a valid CNR from the development dataset
2. malformed CNR format (400)
3. a CNR the dataset does not hold (404)
4. a case with a complete timeline
5. a case with incomplete data
6. a pending case
7. a disposed case
8. a case with orders
9. a case without orders
10. the service failing behind the route (500, no traceback)
11. the authorised provider refusing (503) and the development
    provider being selected by configuration
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cases.provider import DEFAULT_DATASET, reset_provider

CNR_SHAPE = re.compile(r"^[A-Z]{4}[0-9]{12}$")
NOT_AVAILABLE = "Not available in the record."


# =========================================================
# FIXTURES
# =========================================================


@pytest.fixture(scope="session")
def app():
    from main import app as application

    return application


@pytest.fixture()
def client(app):
    """A client that lets server errors reach the handlers.

    Without this, an unexpected exception inside a route is re-raised
    into the test instead of travelling through the application's own
    error handler — which is precisely what test 10 has to observe.
    """
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client

    reset_provider()


@pytest.fixture(scope="session")
def records() -> dict[str, dict]:
    """Every record in the development dataset, keyed by CNR."""
    if not DEFAULT_DATASET.exists():
        pytest.skip(f"dataset not built: {DEFAULT_DATASET}")

    loaded: dict[str, dict] = {}

    for line in DEFAULT_DATASET.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue

        record = json.loads(line)
        loaded[record.get("cnr_number", "")] = record

    return loaded


def pick(records: dict[str, dict], **conditions) -> str:
    """The CNR of the first record satisfying every condition.

    Conditions are ``(field, predicate)`` pairs. A missing candidate is
    a test failure, not a skip: the dataset is committed, so a record
    the assertions were written against disappearing is a real change
    somebody has to look at.
    """
    for cnr, record in sorted(records.items()):
        if all(predicate(record.get(field)) for field, predicate in conditions.items()):
            return cnr

    raise AssertionError(f"no development record satisfies {list(conditions)}")


def has_value(value) -> bool:
    return bool(value) and value != NOT_AVAILABLE


def is_empty(value) -> bool:
    return not value or value == NOT_AVAILABLE


# =========================================================
# 1 — VALID CNR
# =========================================================


def test_valid_cnr_returns_the_case(client, records):
    cnr = "MHPU210000042026"
    assert cnr in records, "the seed CNR must be in the dataset"

    response = client.get(f"/api/cases/cnr/{cnr}")

    assert response.status_code == 200
    body = response.json()

    assert body["success"] is True
    assert body["case"]["cnr_number"] == cnr
    assert body["data_source"]["provider"] == "development"
    assert body["data_source"]["live_ecourts_data"] is False

    case = body["case"]
    for field in (
        "case_type",
        "filing_number",
        "filing_date",
        "registration_number",
        "case_status",
        "court_name",
        "court_state",
        "petitioner_name",
        "respondents_list",
        "case_history_timeline",
        "timeline",
        "orders",
        "calculated_metrics",
    ):
        assert field in case, f"{field} missing from the response"


def test_cnr_is_normalised_before_lookup(client, records):
    """Lower case and pasted separators are cleaned, not rejected."""
    expected = "MHPU210000042026"

    for variant in (
        expected.lower(),
        " mhpu210000042026 ",
        "MHPU-2100-0004-2026",
        "MHPU 2100 0004 2026",
    ):
        response = client.get(f"/api/cases/cnr/{variant}")
        assert response.status_code == 200, f"{variant!r} should resolve"
        assert response.json()["case"]["cnr_number"] == expected


def test_case_shaped_like_the_screen_expects(client):
    case = client.get("/api/cases/cnr/MHPU210000042026").json()["case"]

    assert isinstance(case["respondents_list"], list)
    assert isinstance(case["case_history_timeline"], list)
    assert isinstance(case["orders"], list)
    assert isinstance(case["timeline"], list)

    metrics = case["calculated_metrics"]
    assert metrics["respondent_count"] >= 1
    assert metrics["total_case_age_days"] >= 0
    assert metrics["total_hearings_scheduled"] == len(case["case_history_timeline"])


# =========================================================
# 2 — MALFORMED CNR
# =========================================================


@pytest.mark.parametrize(
    "value",
    [
        "not-a-cnr",
        "MHPU21000004202",      # 15 characters
        "MHPU2100000420260",    # 17 characters
        "1234567890123456",     # digits where letters belong
        "MHPU21000004202A",     # letter where a digit belongs
        "MHP!210000042026",     # punctuation
        "XXXXXXXXXXXXXXXX",     # letters all the way through
    ],
)
def test_malformed_cnr_is_rejected(client, value):
    response = client.get(f"/api/cases/cnr/{value}")

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "Invalid CNR" in detail or "required" in detail.lower()
    assert "Traceback" not in response.text
    assert "File \"" not in response.text


def test_empty_cnr_never_reaches_the_provider(client):
    """An empty segment has no route to fall through to."""
    response = client.get("/api/cases/cnr/")

    assert response.status_code in (400, 404, 422)


# =========================================================
# 3 — CNR NOT FOUND
# =========================================================


def test_unknown_cnr_is_404(client):
    response = client.get("/api/cases/cnr/MHPU999999992026")

    assert response.status_code == 404
    detail = response.json()["detail"]
    assert "MHPU999999992026" in detail
    assert "Traceback" not in response.text


def test_unknown_cnr_is_not_confused_with_a_bad_one(client):
    """A well formed number the dataset lacks is a 404, never a 400."""
    response = client.get("/api/cases/cnr/MHPU000000002020")

    assert response.status_code == 404


# =========================================================
# 4 — COMPLETE TIMELINE
# =========================================================


def test_timeline_is_chronological(client, records):
    cnr = pick(
        records,
        case_history_timeline=lambda rows: bool(rows) and len(rows) >= 3,
    )

    case = client.get(f"/api/cases/cnr/{cnr}").json()["case"]
    timeline = case["timeline"]

    assert timeline, "a case with history must produce a timeline"

    dated = [event["date"] for event in timeline if event["date"]]
    assert dated == sorted(dated), "timeline must run oldest first"
    assert dated, "at least one event must carry a date"

    # The framing events add to the history, they do not replace it:
    # the hearings are all still there, with filing in front of them.
    kinds = {event["event"] for event in timeline}
    assert "Case filed" in kinds
    assert len(timeline) >= len(case["case_history_timeline"]) + 1


def test_timeline_starts_with_filing_and_registration(client, records):
    """Where registration happened after filing, both are their own event.

    A record whose registration date equals its filing date gets one
    event, not two saying the same thing on the same day — which is why
    the pick below asks for the two dates to differ.
    """
    cnr = next(
        candidate
        for candidate, record in sorted(records.items())
        if record.get("filing_date")
        and record.get("registration_date")
        and record["registration_date"] != record["filing_date"]
        and record.get("case_history_timeline")
        and min(
            (row.get("business_on_date") or row.get("hearing_date") or "9999-99-99")
            for row in record["case_history_timeline"]
        )
        > record["registration_date"]
    )
    record = records[cnr]

    timeline = client.get(f"/api/cases/cnr/{cnr}").json()["case"]["timeline"]
    first_two = [event["event"] for event in timeline[:2]]

    assert "Case filed" in first_two[0]
    assert "Case registered" in first_two[1]
    assert timeline[0]["date"] == records[cnr]["filing_date"]
    assert timeline[1]["date"] == records[cnr]["registration_date"]


def test_timeline_events_carry_only_real_values(client, records):
    cnr = pick(records, case_history_timeline=lambda rows: bool(rows))

    timeline = client.get(f"/api/cases/cnr/{cnr}").json()["case"]["timeline"]

    for event in timeline:
        assert set(event) == {"date", "event", "description", "purpose", "stage"}
        if event["date"]:
            assert re.match(r"^\d{4}-\d{2}-\d{2}$", event["date"])
        assert event["event"].strip()


def test_hearing_history_runs_oldest_first(client, records):
    cnr = pick(records, case_history_timeline=lambda rows: bool(rows) and len(rows) >= 3)

    rows = client.get(f"/api/cases/cnr/{cnr}").json()["case"]["case_history_timeline"]
    dates = [row["business_on_date"] or row["hearing_date"] for row in rows if row["business_on_date"] or row["hearing_date"]]

    assert dates == sorted(dates)


def test_history_rows_keep_their_count(client, records):
    """Sorting and timeline building never add or drop a hearing."""
    for cnr, record in sorted(records.items())[:20]:
        source_rows = record.get("case_history_timeline") or []
        served = client.get(f"/api/cases/cnr/{cnr}").json()["case"]

        assert len(served["case_history_timeline"]) == len(source_rows)
        assert served["calculated_metrics"]["total_hearings_scheduled"] == len(source_rows)


# =========================================================
# 5 — INCOMPLETE DATA
# =========================================================


def test_missing_fields_come_back_empty_not_invented(client, records):
    cnr = pick(records, court_district=is_empty)

    case = client.get(f"/api/cases/cnr/{cnr}").json()["case"]

    # The record says the value was not in the source. Nothing has been
    # filled in to make the card look tidier.
    assert case["court_district"] in ("", NOT_AVAILABLE)
    assert case["cnr_number"] == cnr
    assert case["case_status"]

    assert "court_complex" in case
    assert "district" not in case.get("court_district", "")


def test_no_next_hearing_value_means_no_next_hearing_event():
    """A record with no listing date gets no listing event.

    Driven straight off ``cases.timeline`` with a bare shape, because
    every pending record in the development dataset happens to carry a
    date — the empty case still has to behave, whatever the data does.
    """
    from cases.timeline import build_timeline

    events = build_timeline(
        {
            "case_status": "Case pending",
            "filing_date": "2026-01-02",
            "registration_date": "",
            "next_hearing_date": "",
            "case_history_timeline": [
                {"business_on_date": "2026-01-07", "purpose_of_hearing": "Hearing"},
            ],
        }
    )

    assert [e["event"] for e in events] == ["Case filed", "Hearing"]
    assert not [e for e in events if e["event"] == "Next hearing"]


def test_undated_events_are_kept_and_sorted_last():
    """A missing date loses the position, not the event."""
    from cases.timeline import build_timeline

    events = build_timeline(
        {
            "case_status": "Case disposed",
            "filing_date": "",
            "case_history_timeline": [
                {"business_on_date": "", "hearing_date": "", "purpose_of_hearing": "Listed"},
                {"business_on_date": "2026-03-01", "purpose_of_hearing": "Reply/Say"},
            ],
        }
    )

    assert len(events) == 2
    assert events[-1]["date"] == ""
    assert events[-1]["event"] == "Listed"
    assert events[0]["date"] == "2026-03-01"


def test_incomplete_case_still_answers_with_200(client, records):
    """Half a record is still a record: the API does not 404 on gaps."""
    sparsest = min(
        records,
        key=lambda cnr: sum(
            1
            for value in records[cnr].values()
            if value not in ("", [], None, NOT_AVAILABLE)
        ),
    )

    response = client.get(f"/api/cases/cnr/{sparsest}")

    assert response.status_code == 200
    assert response.json()["case"]["cnr_number"] == sparsest


# =========================================================
# 6 — PENDING CASE
# =========================================================


def test_pending_case(client, records):
    cnr = pick(
        records,
        case_status=lambda value: "pending" in str(value).lower(),
        next_hearing_date=has_value,
        case_history_timeline=lambda rows: bool(rows),
    )

    case = client.get(f"/api/cases/cnr/{cnr}").json()["case"]

    assert "pending" in case["case_status"].lower()
    assert case["next_hearing_date"]
    assert case["disposal_date"] in ("", None, NOT_AVAILABLE)

    next_events = [e for e in case["timeline"] if e["event"] == "Next hearing"]
    assert len(next_events) == 1
    assert next_events[0]["date"] == case["next_hearing_date"]

    # The listing sits after everything the court has already done.
    dates = [e["date"] for e in case["timeline"] if e["date"]]
    assert dates.index(case["next_hearing_date"]) == len(dates) - 1


# =========================================================
# 7 — DISPOSED CASE
# =========================================================


def test_disposed_case(client, records):
    cnr = pick(
        records,
        case_status=lambda value: "disposed" in str(value).lower(),
        disposal_date=has_value,
    )

    case = client.get(f"/api/cases/cnr/{cnr}").json()["case"]

    assert "disposed" in case["case_status"].lower()
    assert case["disposal_date"]

    # A disposed matter cannot still be waiting for a date: whatever
    # listing the capture held, no "Next hearing" event is offered.
    assert not [e for e in case["timeline"] if e["event"] == "Next hearing"]


def test_disposed_case_can_have_no_next_hearing_date(client, records):
    cnr = pick(
        records,
        case_status=lambda value: "disposed" in str(value).lower(),
        next_hearing_date=is_empty,
    )

    case = client.get(f"/api/cases/cnr/{cnr}").json()["case"]
    assert case["next_hearing_date"] in ("", None, NOT_AVAILABLE)


# =========================================================
# 8 / 9 — WITH AND WITHOUT ORDERS
# =========================================================


def test_case_with_orders(client, records):
    cnr = pick(records, orders=lambda orders: bool(orders))

    case = client.get(f"/api/cases/cnr/{cnr}").json()["case"]

    assert case["orders"]

    for order in case["orders"]:
        assert set(order) == {
            "order_type",
            "order_number",
            "order_date",
            "order_details",
            "order_section",
        }
        # The capture's displayPdf(...) javascript must not survive the
        # build: it is the court site's, it is not usable here, and it
        # does not belong in an API response.
        assert "displayPdf" not in json.dumps(order)

    order_events = [
        e for e in case["timeline"] if "order passed" in e["event"].lower()
    ]
    assert len(order_events) == len(case["orders"])


def test_case_without_orders(client, records):
    cnr = pick(records, orders=lambda orders: not orders)

    case = client.get(f"/api/cases/cnr/{cnr}").json()["case"]

    assert case["orders"] == []
    assert not [
        e for e in case["timeline"] if "order passed" in e["event"].lower()
    ]

    # An empty order list is still a successful lookup.
    response = client.get(f"/api/cases/cnr/{cnr}")
    assert response.status_code == 200


# =========================================================
# 10 — THE SERVICE FAILING BEHIND THE ROUTE
# =========================================================


def test_unexpected_failure_is_a_bare_500(client, monkeypatch):
    def explode(*_args, **_kwargs):
        raise RuntimeError("connection to case_store exploded at /srv/secret.sql")

    monkeypatch.setattr("cases.routes.get_provider", lambda: _FailingProvider(explode))

    response = client.get("/api/cases/cnr/MHPU210000042026")

    assert response.status_code == 500
    body = response.text
    assert "Traceback" not in body
    assert "/srv/secret.sql" not in body
    assert "RuntimeError" not in body
    assert response.json()["detail"]


def test_case_data_error_is_a_message_not_a_crash(client, monkeypatch):
    from cases.provider import CaseDataError

    def fail(*_args, **_kwargs):
        raise CaseDataError("the dataset file disappeared")

    monkeypatch.setattr("cases.routes.get_provider", lambda: _FailingProvider(fail))

    response = client.get("/api/cases/cnr/MHPU210000042026")

    assert response.status_code == 500
    assert response.json()["detail"] == "The case record could not be read."
    assert "Traceback" not in response.text


def test_list_failure_is_contained(client, monkeypatch):
    from cases.provider import ProviderUnavailableError

    def refuse(*_args, **_kwargs):
        raise ProviderUnavailableError("no source configured")

    monkeypatch.setattr("cases.routes.get_provider", lambda: _FailingProvider(refuse))

    response = client.get("/api/cases")

    assert response.status_code == 503
    assert response.json()["detail"] == "no source configured"
    assert "Traceback" not in response.text


class _FailingProvider:
    """A provider wired to one callable, for failure-path tests."""

    def __init__(self, behaviour):
        self._behaviour = behaviour

    def get_case(self, cnr):
        return self._behaviour(cnr)

    def list_cases(self, **kwargs):
        return self._behaviour(**kwargs)

    def describe(self):
        return {"provider": "failing", "available": False}


# =========================================================
# 11 — PROVIDER SELECTION
# =========================================================


def test_authorised_provider_refuses_until_it_exists(client, monkeypatch):
    monkeypatch.setenv("CASE_DATA_PROVIDER", "external")
    monkeypatch.setattr("cases.provider._provider", None, raising=False)
    reset_provider()

    try:
        response = client.get("/api/cases/cnr/MHPU210000042026")

        assert response.status_code == 503
        assert "authorised" in response.json()["detail"].lower()
        assert "Traceback" not in response.text
    finally:
        monkeypatch.delenv("CASE_DATA_PROVIDER", raising=False)
        reset_provider()


def test_development_provider_is_the_default(client):
    reset_provider()

    body = client.get("/api/cases/meta").json()
    source = body["data_source"]

    assert source["provider"] == "development"
    assert source["available"] is True
    assert source["records"] >= 100
    assert source["live_ecourts_data"] is False
    assert "not" in source["disclaimer"].lower()


# =========================================================
# LISTING / FILTERS / DATASET INTEGRITY
# =========================================================


def test_list_endpoint_pages(client, records):
    body = client.get("/api/cases?limit=5").json()

    assert body["success"] is True
    assert len(body["items"]) == 5
    assert body["total"] == len(records)
    assert body["total_pages"] == -(-len(records) // 5)
    assert body["data_source"]["live_ecourts_data"] is False


def test_list_filters_by_status(client, records):
    expected_pending = sum(
        1 for r in records.values() if "pending" in r["case_status"].lower()
    )

    body = client.get("/api/cases?status=pending&limit=100").json()

    assert body["total"] == expected_pending
    assert all(
        "pending" in item["case_status"].lower() for item in body["items"]
    )


def test_list_searches_by_cnr(client):
    body = client.get("/api/cases?q=MHPU210000042026").json()

    assert body["total"] == 1
    assert body["items"][0]["cnr_number"] == "MHPU210000042026"


def test_every_dataset_record_is_reachable(client, records):
    """The dataset and the endpoint agree: one lookup each, all 200."""
    sample = sorted(records)[:25]

    for cnr in sample:
        response = client.get(f"/api/cases/cnr/{cnr}")
        assert response.status_code == 200, f"{cnr} -> {response.status_code}"


def test_dataset_shape():
    if not DEFAULT_DATASET.exists():
        pytest.skip("dataset not built")

    lines = [
        line
        for line in Path(DEFAULT_DATASET).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert len(lines) >= 100, "the development dataset should hold the team's captures"

    cnrs = set()
    for line in lines:
        record = json.loads(line)
        cnr = record["cnr_number"]

        assert CNR_SHAPE.match(cnr), f"{cnr} is not a CNR"
        assert cnr not in cnrs, f"{cnr} appears twice"
        cnrs.add(cnr)

        assert "displayPdf" not in line, "raw page javascript leaked into the dataset"
        assert "app_token=" not in line, "a source session token leaked into the dataset"

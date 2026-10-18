"""Tests for the two plug-in interfaces the other members connect to.

Pure Python — no HTTP, no model. Run from this directory:

    .venv/bin/pytest test_member_interfaces.py -v

Two seams, one rule each:

  * Member 2's incident-classification model (incident_classification)
    plugs in through `register_classifier` or
    `NYAYMITRA_INCIDENT_CLASSIFIER_URL`. Until then the adapter
    returns *nothing* — the analysis falls back to keyword matching
    and reports that source. No payload is ever synthesised, and a
    broken or shapeless model answer counts as no answer.

  * Member 2's urgency model (urgency_adapter) plugs in the same way.
    Until then every result is `{"status": "not_available", ...}` —
    never a LOW/MEDIUM/HIGH band nobody computed.

  * Member 1's incident knowledge (incident_knowledge) is a loader
    over structured files: the full documented schema is consumed
    when present, wrong-shaped entries are skipped, and a missing
    file is a note rather than an exception.
"""

from __future__ import annotations

import json

import pytest

from incident_classification import (
    CLASSIFIER_URL_ENV,
    NOT_CONNECTED_MESSAGE,
    classify,
    clear_classifier,
    classifier_status,
    register_classifier,
)
from incident_knowledge import (
    DEV_EXAMPLE_ENV,
    KNOWLEDGE_DIR_ENV,
    load_knowledge,
)
from urgency_adapter import (
    URGENCY_MODEL_URL_ENV,
    NOT_CONNECTED_MESSAGE as URGENCY_NOT_CONNECTED,
    assess_urgency,
    clear_urgency_model,
    register_urgency_model,
    urgency_status,
)


# ---------------------------------------------------------------------------
# MEMBER 2 — incident classification adapter
# ---------------------------------------------------------------------------

@pytest.fixture
def no_classifier():
    """A clean slate: nothing registered, no URL set."""
    clear_classifier()
    yield
    clear_classifier()


def test_classifier_reports_itself_as_not_connected(no_classifier, monkeypatch):
    monkeypatch.delenv(CLASSIFIER_URL_ENV, raising=False)
    status = classifier_status()
    assert status["connected"] is False
    assert status["source"] == "not_connected"
    assert "not connected yet" in status["message"]


def test_unconnected_classifier_returns_none_not_a_guess(no_classifier, monkeypatch):
    monkeypatch.delenv(CLASSIFIER_URL_ENV, raising=False)
    assert classify("Someone took my parcel") is None


def test_registered_classifier_payload_is_consumed_and_normalised(no_classifier):
    def model(text, language):
        return {
            "incident_category": "otp_fraud",
            "confidence": 0.82,
            "language": language,
            "facts": {"channel": "phone call"},
            "missing_information": ["When did this happen?"],
            "some_future_field": "ignored",
        }

    register_classifier(model)
    result = classify("Someone asked for my OTP", language="mr")

    assert classifier_status()["connected"] is True
    assert result["incident_category"] == "otp_fraud"
    assert result["confidence"] == 0.82
    assert result["language"] == "mr"
    assert result["facts"] == {"channel": "phone call"}
    assert result["missing_information"] == ["When did this happen?"]
    assert "some_future_field" not in result


def test_classifier_payload_cannot_smuggle_invalid_values(no_classifier):
    def model(text, language):
        return {
            "incident_category": "   ",          # blank: no category
            "confidence": 7.5,                   # out of range: dropped
            "facts": {"when": ["not", "a", "scalar"]},  # wrong type: dropped
            "missing_information": "not a list",  # wrong type: dropped
        }

    register_classifier(model)
    result = classify("anything")
    # Every invalid field became None/empty — never a plausible default.
    assert result is None  # nothing usable survived, so: no answer


def test_empty_model_payload_is_not_an_answer(no_classifier):
    register_classifier(lambda text, language: {})
    assert classify("anything") is None


def test_raising_model_degrades_to_not_connected(no_classifier):
    def broken(text, language):
        raise RuntimeError("model exploded")

    register_classifier(broken)
    assert classify("anything") is None
    assert classifier_status()["connected"] is True  # registered, but
    # the *payload* was absent, so the analysis treats it as unclassified.


def test_unreachable_classifier_url_returns_none(no_classifier, monkeypatch):
    monkeypatch.setenv(CLASSIFIER_URL_ENV, "http://127.0.0.1:9/classify")
    assert classify("anything") is None


# ---------------------------------------------------------------------------
# MEMBER 2 — urgency adapter
# ---------------------------------------------------------------------------

@pytest.fixture
def no_urgency_model():
    clear_urgency_model()
    yield
    clear_urgency_model()


def test_urgency_without_a_model_is_not_available(no_urgency_model, monkeypatch):
    monkeypatch.delenv(URGENCY_MODEL_URL_ENV, raising=False)
    result = assess_urgency("Someone threatened me")
    assert result == {
        "status": "not_available",
        "message": URGENCY_NOT_CONNECTED,
    }
    assert "level" not in result
    assert urgency_status()["connected"] is False


def test_connected_urgency_model_is_used(no_urgency_model):
    def model(text, classification):
        return {
            "status": "available",
            "level": "high",
            "message": "Immediate safety concern described.",
            "basis": "model v1",
        }

    register_urgency_model(model)
    result = assess_urgency("Someone threatened me", {"incident_category": "x"})
    assert result["status"] == "available"
    assert result["level"] == "high"
    assert result["source"] == "incident-urgency-model"
    assert urgency_status()["connected"] is True


def test_partial_or_invalid_model_answer_degrades_to_not_available(no_urgency_model):
    # "available" without a level: a half-answer must not render.
    register_urgency_model(lambda text, cls: {"status": "available"})
    assert assess_urgency("x")["status"] == "not_available"

    # An unknown level is not a level.
    register_urgency_model(
        lambda text, cls: {"status": "available", "level": "critical"}
    )
    assert assess_urgency("x")["status"] == "not_available"

    # Neither is a bare level with no status.
    register_urgency_model(lambda text, cls: {"level": "high"})
    assert assess_urgency("x")["status"] == "not_available"


def test_raising_urgency_model_degrades_to_not_available(no_urgency_model):
    def broken(text, classification):
        raise RuntimeError("boom")

    register_urgency_model(broken)
    result = assess_urgency("x")
    assert result["status"] == "not_available"
    assert result["message"] == URGENCY_NOT_CONNECTED


# ---------------------------------------------------------------------------
# MEMBER 1 — incident knowledge: the full documented schema
# ---------------------------------------------------------------------------

def test_full_knowledge_schema_is_consumed(tmp_path, monkeypatch):
    (tmp_path / "incident_categories.json").write_text(
        json.dumps(
            {
                "categories": [
                    {
                        "id": "threat_demand",
                        "label": "A threat with a demand for money",
                        "keywords": ["threatened me", "demanded money"],
                        "possible_legal_issue": (
                            "Based on what you described, this may involve "
                            "a criminal matter related to threats."
                        ),
                        "urgency_indicators": [
                            "A threat of immediate harm."
                        ],
                        "warnings": ["Category warning from Member 1."],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "incident_next_steps.json").write_text(
        json.dumps([{"category_id": "threat_demand",
                     "steps": ["Keep the demand messages."]}]),
        encoding="utf-8",
    )
    (tmp_path / "incident_questions.json").write_text(
        json.dumps({"questions": {"threat_demand": ["Who made the demand?"]}}),
        encoding="utf-8",
    )
    # "facts" is an accepted synonym for "evidence" in this file.
    (tmp_path / "incident_facts.json").write_text(
        json.dumps({"facts": {"threat_demand": ["Recordings of the calls."]}}),
        encoding="utf-8",
    )
    monkeypatch.setenv(KNOWLEDGE_DIR_ENV, str(tmp_path))
    monkeypatch.delenv(DEV_EXAMPLE_ENV, raising=False)

    knowledge = load_knowledge()
    assert knowledge.source == "files"

    per_category = knowledge.for_category("threat_demand")
    assert per_category["possible_legal_issue"].startswith(
        "Based on what you described"
    )
    assert per_category["urgency_indicators"] == ["A threat of immediate harm."]
    assert per_category["warnings"] == ["Category warning from Member 1."]
    assert per_category["next_steps"] == ["Keep the demand messages."]
    assert per_category["questions"] == ["Who made the demand?"]
    assert per_category["evidence"] == ["Recordings of the calls."]


def test_unknown_category_returns_empty_sections(tmp_path, monkeypatch):
    (tmp_path / "incident_categories.json").write_text(
        json.dumps({"categories": [{"id": "a", "label": "A"}]}),
        encoding="utf-8",
    )
    monkeypatch.setenv(KNOWLEDGE_DIR_ENV, str(tmp_path))
    monkeypatch.delenv(DEV_EXAMPLE_ENV, raising=False)

    empty = load_knowledge().for_category(None)
    assert empty == {
        "next_steps": [],
        "questions": [],
        "evidence": [],
        "possible_legal_issue": "",
        "urgency_indicators": [],
        "warnings": [],
    }
    unknown = load_knowledge().for_category("not-in-the-file")
    assert unknown["possible_legal_issue"] == ""
    assert unknown["urgency_indicators"] == []


def test_wrong_typed_new_fields_are_skipped(tmp_path, monkeypatch):
    (tmp_path / "incident_categories.json").write_text(
        json.dumps(
            {
                "categories": [
                    {
                        "id": "a",
                        "label": "A",
                        "possible_legal_issue": 42,
                        "urgency_indicators": "not a list",
                        "warnings": {"not": "a list"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(KNOWLEDGE_DIR_ENV, str(tmp_path))
    monkeypatch.delenv(DEV_EXAMPLE_ENV, raising=False)

    per_category = load_knowledge().for_category("a")
    assert per_category["possible_legal_issue"] == ""
    assert per_category["urgency_indicators"] == []
    assert per_category["warnings"] == []

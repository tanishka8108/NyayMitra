"""Unit tests for the "What Happened?" incident analysis.

Pure Python — no HTTP, no model. Run from this directory:

    .venv/bin/pytest test_incident_analysis.py -v

What is under test, in one line each:

  * the analysis hedges instead of concluding (and warns, at low
    confidence, in exactly the agreed words);
  * `facts` are substrings of what the person actually wrote —
    extraction may not add a date, an amount or an identifier that is
    not in the description;
  * the incident workflow never maps the description to a court case
    stage — stage guidance belongs to the case workflow, and the
    incident response carries neither a stage nor a `guidance` block;
  * urgency is the adapter's honest "not available" until a model
    exists — never a fabricated LOW/MEDIUM/HIGH band;
  * Member 1's incident knowledge files are read when they exist,
    tolerated when they do not, and never invented when they are
    missing.
"""

from __future__ import annotations

import json
import re

import pytest

from conversation_context import ConversationContextStore
from incident_analysis import LOW_CONFIDENCE_WARNING, analyze_incident
from incident_knowledge import (
    DEV_EXAMPLE_ENV,
    KNOWLEDGE_DIR_ENV,
    find_category,
    knowledge_status,
    load_knowledge,
)

# ---------------------------------------------------------------------------
# A vague description and a detailed one. The second carries everything
# an analysis could hope for: when, where, who, an amount, an identifier
# and a court.
# ---------------------------------------------------------------------------

VAGUE = "something happened"

DETAILED = (
    "On 15.10.2026 I paid Rs. 25,000 to Mr. Rahul Sharma by UPI "
    "transaction id TXN-889912 in Pune. The Pune Civil Court adjourned "
    "my case because the judge was not available. I have receipts and "
    "messages about it. My case number is CASE/2026/4471 and my CNR is "
    "MHMM0100123452026."
)

DATE_PATTERN = r"\b\d{1,2}[./-]\d{1,2}[./-]\d{4}\b"
SECTION_PATTERN = r"[Ss]ection\s+\d+[A-Z]?"


# ---------------------------------------------------------------------------
# INPUT HANDLING
# ---------------------------------------------------------------------------

def test_empty_description_is_refused():
    with pytest.raises(ValueError):
        analyze_incident("   \n  ")


def test_analysis_returns_the_documented_fields():
    result = analyze_incident(VAGUE)
    assert {
        "mode",
        "original_input",
        "what_user_described",
        "possible_issue",
        "simple_explanation",
        "facts",
        "missing_information",
        "next_steps",
        "evidence_to_preserve",
        "urgency",
        "warnings",
        "confidence",
        "incident_category",
        "classification",
        "knowledge",
        "disclaimer",
    } <= set(result)
    assert result["mode"] == "incident"
    assert "guidance" not in result  # the incident workflow has no stage


def test_description_is_echoed_untouched():
    description = "  My   landlord took  my deposit.  "
    result = analyze_incident(description)
    assert result["what_user_described"] == "My landlord took my deposit."
    assert result["original_input"] == description


# ---------------------------------------------------------------------------
# HEDGING — the language rules the analysis lives by
# ---------------------------------------------------------------------------

def test_vague_description_is_hedged_not_concluded():
    result = analyze_incident(VAGUE)
    issue = result["possible_issue"]
    assert "Based on what you described" in issue
    assert "not sufficient to determine" in issue
    # No confident category is claimed for a description that cannot
    # support one — and no court stage either: there is no stage
    # lookup in this workflow at all.
    assert result["incident_category"] is None
    assert "guidance" not in result
    assert "court stage" not in issue.lower()


def test_low_confidence_carries_the_agreed_warning():
    result = analyze_incident(VAGUE)
    assert result["confidence"]["level"] == "low"
    assert LOW_CONFIDENCE_WARNING in result["warnings"]
    assert (
        "More information is needed to understand this situation "
        "accurately."
    ) in result["warnings"]


def test_next_steps_are_phrased_as_options():
    result = analyze_incident("My bail application was rejected yesterday")
    joined = " ".join(result["next_steps"])
    assert "You may consider" in joined
    # Nothing imperative-without-hedge, nothing predicting an outcome.
    assert "will be" not in joined.lower()


def test_every_evidence_note_is_optional_language():
    result = analyze_incident(VAGUE)
    assert result["evidence_to_preserve"]
    assert all(
        note.startswith("You may consider")
        for note in result["evidence_to_preserve"]
    )


def test_analysis_always_disclaims_itself():
    result = analyze_incident(DETAILED)
    assert any("based only on what you described" in w for w in result["warnings"])
    assert result["disclaimer"]


# ---------------------------------------------------------------------------
# NO INVENTED FACTS
# ---------------------------------------------------------------------------

def test_detected_facts_are_substrings_of_the_description():
    result = analyze_incident(DETAILED)
    detected = [f for f in result["facts"] if f["source"] == "detected"]
    assert detected, "the detailed description should yield facts"
    for fact in detected:
        assert fact["value"].lower() in DETAILED.lower(), fact


def test_expected_entities_are_detected():
    result = analyze_incident(DETAILED)
    values = {f["value"] for f in result["facts"]}
    types = {f["type"] for f in result["facts"]}
    assert "15.10.2026" in values
    assert "Rs. 25,000" in values
    assert "TXN-889912" in values
    assert "CASE/2026/4471" in values
    assert "Rahul Sharma" in values
    # The court name may be captured with a leading article; what
    # matters is that the whole name is there, verbatim.
    assert any("Pune Civil Court" in value for value in values)
    assert {"date", "amount", "person", "court"} <= types


def test_no_date_or_section_is_invented():
    for text in (VAGUE, "My bail application was rejected yesterday", DETAILED):
        result = analyze_incident(text)
        rendered = json.dumps(result, ensure_ascii=False)

        for match in re.findall(DATE_PATTERN, rendered):
            assert match in text, f"date {match} was not in the input"
        for match in re.findall(SECTION_PATTERN, rendered):
            assert match in text, f"section {match} was not in the input"


def test_vague_and_detailed_descriptions_are_not_read_the_same():
    vague = analyze_incident(VAGUE)
    detailed = analyze_incident(DETAILED)
    assert vague["confidence"]["score"] < detailed["confidence"]["score"]
    assert detailed["confidence"]["level"] in {"medium", "high"}
    # The basis says what was and was not there, in plain terms.
    assert "no date" in vague["confidence"]["basis"]
    assert "incident category" in vague["confidence"]["basis"]


def test_missing_information_asks_for_what_is_absent():
    result = analyze_incident(VAGUE)
    questions = " ".join(result["missing_information"])
    # Nothing about when/where/who was said, so all three are asked.
    assert "When did this happen" in questions
    assert "Where did it happen" in questions
    assert "Who else was involved" in questions

    answered = analyze_incident(DETAILED)
    answered_questions = " ".join(answered["missing_information"])
    assert "When did this happen" not in answered_questions


# ---------------------------------------------------------------------------
# THE TWO WORKFLOWS MUST NOT BE MIXED — an incident is not a court stage
# ---------------------------------------------------------------------------

def test_incident_input_is_not_mapped_to_a_court_stage():
    """The exact input the old screen answered with "Notice issued to
    respondent": the incident workflow must read it as an incident."""
    result = analyze_incident(
        "I received a legal notice from the other side last week and "
        "do not know what to reply."
    )
    rendered = json.dumps(result, ensure_ascii=False)

    assert result["mode"] == "incident"
    assert "guidance" not in result
    assert "court stage" not in result["possible_issue"].lower()
    assert "court stage" not in result["simple_explanation"].lower()
    # No stage name from the guidance set leaks in as an answer.
    assert "Notice issued to respondent" not in rendered
    assert "MATCHED TO A CASE STAGE" not in rendered


def test_a_case_stage_flavoured_input_still_gets_incident_reading():
    """A bail description used to come back as "Anticipatory bail
    rejected". It is still an incident description here."""
    result = analyze_incident("My bail application was rejected yesterday")
    rendered = json.dumps(result, ensure_ascii=False)
    assert "Anticipatory bail rejected" not in rendered
    # And the reading is honest about what it could not determine.
    assert "Based on what you described" in result["possible_issue"]


def test_urgency_is_the_adapters_answer_and_never_a_fake_band():
    from urgency_adapter import NOT_CONNECTED_MESSAGE

    result = analyze_incident(DETAILED)
    urgency = result["urgency"]
    assert urgency["status"] == "not_available"
    assert urgency["message"] == NOT_CONNECTED_MESSAGE
    # No level, no band — nothing that could render as LOW/MEDIUM/HIGH.
    # (The `level` inside `confidence` is a detail-count, not an
    # urgency verdict; this test is about `urgency` only.)
    assert "level" not in urgency
    assert set(urgency) <= {"status", "message", "knowledge_indicators",
                            "knowledge_indicator_note"}


def test_classification_source_is_reported():
    result = analyze_incident(VAGUE)
    classification = result["classification"]
    assert classification["source"] in {
        "none",
        "keyword_matching",
        "member2_model",
    }
    assert classification["member2_connected"] is False
    # While the model is unconnected, the response says so in words.
    assert "not connected yet" in classification["note"]
    assert any("not connected yet" in w for w in result["warnings"])


def test_prior_description_is_read_together_with_the_follow_up():
    """"It happened yesterday" only means something next to the account
    it refers to."""
    result = analyze_incident(
        "It happened yesterday.",
        prior_description=(
            "Someone called me pretending to be from my bank and "
            "asked for my OTP."
        ),
    )
    assert result["original_input"] == "It happened yesterday."
    assert result["what_user_described"].startswith("Someone called me")
    assert "It happened yesterday." in result["what_user_described"]
    # The "when" is now answered, so it is no longer asked for.
    assert not any(
        "When did this happen" in q for q in result["missing_information"]
    )


# ---------------------------------------------------------------------------
# MEMBER 1'S KNOWLEDGE FILES — present, absent, broken
# ---------------------------------------------------------------------------

def test_knowledge_status_reports_missing_files():
    status = knowledge_status()
    assert status["source"] in {"none", "files"}
    assert set(status["files"]) == {
        "categories",
        "next_steps",
        "questions",
        "facts",
    }
    if status["source"] == "none":
        assert status["notes"], "a missing file should be noted, not hidden"


def test_missing_knowledge_is_announced_not_papered_over():
    knowledge = load_knowledge()
    if knowledge.source == "files":
        pytest.skip("Member 1's knowledge files are present on this machine")
    result = analyze_incident(VAGUE)
    assert any("not loaded yet" in w for w in result["warnings"])
    assert result["knowledge"]["source"] == "none"


def test_malformed_knowledge_file_is_tolerated(tmp_path, monkeypatch):
    (tmp_path / "incident_categories.json").write_text("{not json", encoding="utf-8")
    monkeypatch.setenv(KNOWLEDGE_DIR_ENV, str(tmp_path))
    monkeypatch.delenv(DEV_EXAMPLE_ENV, raising=False)

    knowledge = load_knowledge()
    assert knowledge.categories == []
    assert any("could not be read" in note for note in knowledge.notes)
    # And the analysis still runs.
    assert analyze_incident(VAGUE)["what_user_described"]


def test_wrong_shaped_knowledge_entries_are_skipped(tmp_path, monkeypatch):
    (tmp_path / "incident_categories.json").write_text(
        json.dumps({"categories": [{"label": "no id"}, "a string", {"id": "x"}]}),
        encoding="utf-8",
    )
    monkeypatch.setenv(KNOWLEDGE_DIR_ENV, str(tmp_path))
    monkeypatch.delenv(DEV_EXAMPLE_ENV, raising=False)

    assert load_knowledge().categories == []


def test_real_knowledge_files_are_read_end_to_end(tmp_path, monkeypatch):
    """The shape Member 1 will deliver, exercised through the loader."""
    (tmp_path / "incident_categories.json").write_text(
        json.dumps(
            {
                "categories": [
                    {
                        "id": "parcel_taken",
                        "label": "An item taken without consent",
                        "keywords": ["took my parcel", "parcel", "missing parcel"],
                        "description": "Dev example category for the loader test.",
                        "possible_legal_issue": (
                            "Based on what you described, this may involve "
                            "a dispute over an item taken without consent."
                        ),
                        "urgency_indicators": [
                            "Dev example urgency indicator."
                        ],
                        "warnings": ["Dev example category warning."],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "incident_next_steps.json").write_text(
        json.dumps({"next_steps": {"parcel_taken": ["Keep the delivery receipt."]}}),
        encoding="utf-8",
    )
    (tmp_path / "incident_questions.json").write_text(
        json.dumps({"questions": {"parcel_taken": ["What was in the parcel?"]}}),
        encoding="utf-8",
    )
    (tmp_path / "incident_facts.json").write_text(
        json.dumps({"evidence": {"parcel_taken": ["Track the shipment history."]}}),
        encoding="utf-8",
    )
    monkeypatch.setenv(KNOWLEDGE_DIR_ENV, str(tmp_path))
    monkeypatch.delenv(DEV_EXAMPLE_ENV, raising=False)

    knowledge = load_knowledge()
    assert knowledge.source == "files"
    assert knowledge.available == {
        "categories": True,
        "next_steps": True,
        "questions": True,
        "facts": True,
    }

    result = analyze_incident("Someone took my parcel from the door.")
    assert result["incident_category"] == {
        "id": "parcel_taken",
        "label": "An item taken without consent",
    }
    assert "Keep the delivery receipt." in result["next_steps"]
    assert "Track the shipment history." in result["evidence_to_preserve"]
    assert "What was in the parcel?" in result["missing_information"]
    # The category's own possible-legal-issue wording is used verbatim,
    # with the standing hedge appended after it.
    assert "a dispute over an item taken without consent" in result["possible_issue"]
    assert (
        "The exact legal classification depends on the circumstances."
        in result["possible_issue"]
    )
    # Urgency indicators ride along as clearly-marked general notes —
    # the status stays "not_available": knowledge is not a model.
    assert result["urgency"]["status"] == "not_available"
    assert "Dev example urgency indicator." in result["urgency"]["knowledge_indicators"]
    assert "not an assessment" in result["urgency"]["knowledge_indicator_note"]
    # The category's warnings join the response warnings.
    assert "Dev example category warning." in result["warnings"]
    # The category knowledge is loaded, so the "not loaded" warning
    # must not appear.
    assert not any("not loaded yet" in w for w in result["warnings"])


def test_category_matching_refuses_to_guess(tmp_path, monkeypatch):
    (tmp_path / "incident_categories.json").write_text(
        json.dumps(
            {
                "categories": [
                    {"id": "x", "label": "X", "keywords": ["parcel"]},
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(KNOWLEDGE_DIR_ENV, str(tmp_path))
    monkeypatch.delenv(DEV_EXAMPLE_ENV, raising=False)

    knowledge = load_knowledge()
    assert find_category(knowledge, "my parcel is gone") is not None
    assert find_category(knowledge, "nothing relevant here at all") is None


def test_dev_example_is_marked_and_opt_in(tmp_path, monkeypatch):
    monkeypatch.setenv(KNOWLEDGE_DIR_ENV, str(tmp_path))  # empty directory
    monkeypatch.setenv(DEV_EXAMPLE_ENV, "1")

    knowledge = load_knowledge()
    assert knowledge.source == "dev-example"
    assert any("dev example" in note for note in knowledge.notes)
    assert knowledge.categories[0]["label"].startswith("Dev example")

    result = analyze_incident("this is a dev example")
    assert result["incident_category"]["id"] == "dev_example_only"


# ---------------------------------------------------------------------------
# CONVERSATION CONTEXT — bounded, thread-safe, no database
# ---------------------------------------------------------------------------

def test_conversation_is_created_and_reused():
    store = ConversationContextStore()
    first = store.ensure(None)
    assert first["conversation_id"].startswith("c_")
    assert store.get(first["conversation_id"]) is not None

    same = store.ensure(first["conversation_id"])
    assert same["conversation_id"] == first["conversation_id"]


def test_unknown_conversation_returns_nothing():
    store = ConversationContextStore()
    assert store.get("c_nope") is None
    assert store.known_facts("c_nope") == {}


def test_recording_merges_facts_without_losing_them():
    store = ConversationContextStore()
    state = store.record(
        None,
        role="user",
        content="hello",
        current_intent="incident_analysis",
        incident_category="parcel_taken",
        known_facts={"date_1": "15.10.2026"},
    )
    conversation_id = state["conversation_id"]

    later = store.record(
        conversation_id,
        role="assistant",
        content="hi",
        known_facts={"amount_1": "Rs. 25,000", "date_1": ""},
    )
    assert later["known_facts"] == {
        "date_1": "15.10.2026",   # empty values never overwrite real ones
        "amount_1": "Rs. 25,000",
    }
    assert later["current_intent"] == "incident_analysis"
    assert later["incident_category"] == "parcel_taken"
    assert len(later["messages"]) == 2


def test_message_history_is_bounded():
    store = ConversationContextStore(max_messages=5)
    state = store.ensure(None)
    for index in range(12):
        state = store.record(
            state["conversation_id"], role="user", content=f"m{index}"
        )
    assert len(state["messages"]) == 5
    assert state["messages"][-1]["content"] == "m11"


def test_conversation_count_is_bounded():
    store = ConversationContextStore(max_conversations=3)
    ids = [store.ensure(None)["conversation_id"] for _ in range(6)]
    assert store.size() == 3
    assert store.get(ids[0]) is None  # oldest went first
    assert store.get(ids[-1]) is not None

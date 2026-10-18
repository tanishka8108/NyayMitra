"""Unit tests for the case companion — the "does it say so?" tests.

Pure Python, no HTTP, no model. Run from this directory:

    .venv/bin/pytest test_case_companion.py -v

The companion exists to answer questions about a case *from the case
information supplied with the question*. Its most important behaviour
is what it does when that information does not contain the answer:
it says the information does not state it, and never fills the gap
with a plausible guess.
"""

from __future__ import annotations

import re

from case_companion import answer_case_question, classify_question

# ---------------------------------------------------------------------------
# A case record shaped like Member 4's My Cases data. It has a stage, a
# next date, a timeline with an adjournment that gives a reason, and one
# order — and it deliberately has *no* case status, so the "not stated"
# path has something to be absent from.
# ---------------------------------------------------------------------------

CONTEXT = {
    "case_number": "CASE/2026/4471",
    "cnr": "MHMM0100123452026",
    "court_name": "Pune Civil Court",
    "current_case_stage": "Case adjourned for want of time",
    "next_hearing_date": "15.10.2026",
    "petitioner_name": "Asha Patil",
    "respondent_name": "Ramesh Kumar",
    "case_history_timeline": [
        {
            "date": "01.07.2026",
            "event": "Case filed",
            "description": "Original petition filed with documents.",
        },
        {
            "date": "22.09.2026",
            "event": "Adjourned",
            "description": "Matter adjourned because the judge was on leave.",
        },
    ],
    "orders": [
        {
            "date": "10.08.2026",
            "order_text": (
                "The petitioner is directed to file a written reply "
                "within four weeks from today."
            ),
        },
    ],
}

# The same case, minus the reason: an adjournment on record with
# nothing saying why.
CONTEXT_NO_REASON = {
    "case_history_timeline": [
        {
            "date": "22.09.2026",
            "event": "Adjourned",
            "description": "Matter adjourned to 15.10.2026.",
        }
    ],
}


def _ask(question: str, context: dict | None = CONTEXT) -> dict:
    return answer_case_question(question, context)


# ---------------------------------------------------------------------------
# ADJOURNMENT — the case the whole feature was named for
# ---------------------------------------------------------------------------

def test_absent_reason_is_said_to_be_absent():
    result = _ask("Why was the case adjourned?", CONTEXT_NO_REASON)
    assert result["question_type"] == "adjournment_reason"
    assert result["grounded"] is False
    assert (
        "The available case information does not state the reason for "
        "the adjournment."
    ) in result["answer"]
    assert "reason for the adjournment" in result["missing_information"]


def test_present_reason_is_quoted_from_the_record():
    result = _ask("Why was the case adjourned?", CONTEXT)
    assert result["grounded"] is True
    assert "judge was on leave" in result["answer"]
    assert result["source"]["field"] == "case_history_timeline[1]"
    # The answer is the record's words, not a paraphrase that could
    # drift: the entry text is quoted.
    assert "Matter adjourned because the judge was on leave" in result["answer"]


def test_no_adjournment_mentioned_is_not_invented():
    result = _ask("Why was the case adjourned?", {})
    assert result["answer"] == (
        "The available case information does not mention any adjournment."
    )
    assert result["grounded"] is False


# ---------------------------------------------------------------------------
# HEARING DATE / STAGE / STATUS
# ---------------------------------------------------------------------------

def test_next_hearing_date_is_quoted_when_present():
    result = _ask("When is the next hearing?")
    assert result["grounded"] is True
    assert "15.10.2026" in result["answer"]
    assert result["source"]["field"] == "next_hearing_date"


def test_absent_next_hearing_date_is_said_to_be_absent():
    result = answer_case_question("When is the next hearing?", {})
    assert result["grounded"] is False
    assert (
        "The available case information does not state the next hearing "
        "date."
    ) in result["answer"]
    assert "next_hearing_date" in result["missing_information"]


def test_current_stage_is_reported_and_explained_via_guidance():
    result = _ask("What stage is my case at?")
    assert result["grounded"] is True
    assert "Case adjourned for want of time" in result["answer"]
    # The explanation of the stage is the existing guidance set's own
    # wording — reused, not restated by this module.
    assert "guidance set that stage means" in result["answer"]
    assert result["next_steps"]
    assert "You may consider" in result["next_steps"][0]


def test_absent_status_is_said_to_be_absent():
    # CONTEXT carries no case_status at all.
    result = _ask("What is the status of my case?")
    assert result["question_type"] == "case_status"
    assert result["grounded"] is False
    assert (
        "The available case information does not state the status of "
        "the case."
    ) in result["answer"]
    # And it does not smuggle in a status-looking word of its own.
    for invented in ("pending", "under trial", "disposed", "closed", "active"):
        assert invented not in result["answer"].lower()


def test_present_status_is_reported():
    context = dict(CONTEXT, case_status="Pending before the court")
    result = _ask("What is the status of my case?", context)
    assert result["grounded"] is True
    assert "Pending before the court" in result["answer"]


# ---------------------------------------------------------------------------
# ORDERS — plain English, but only when the words are there
# ---------------------------------------------------------------------------

def test_order_is_explained_in_plain_english_when_present():
    result = _ask("Explain the order.")
    assert result["question_type"] == "order_explanation"
    assert result["grounded"] is True
    assert result["simplified_order"] is not None
    plain = result["simplified_order"]["simple_english"]
    # The existing simplification engine did the work: a court order's
    # "is directed to file" comes back as plain "must file".
    assert "four weeks" in plain
    assert "must file" in plain
    # The original words are handed back alongside the rewrite.
    assert "is directed to file" in result["simplified_order"]["original_text"]


def test_missing_order_text_is_said_to_be_missing():
    result = answer_case_question("Explain the order.", {})
    assert result["grounded"] is False
    assert (
        "The available case information does not include the text of "
        "any order, so it cannot be explained here."
    ) in result["answer"]
    assert result["simplified_order"] is None


# ---------------------------------------------------------------------------
# WHAT TO DO NEXT — reused guidance, only from a stated stage
# ---------------------------------------------------------------------------

def test_next_step_comes_from_the_stated_stage():
    result = _ask("What should I do next?")
    assert result["grounded"] is True
    assert result["next_steps"]
    assert "stage recorded in the available case information" in result["answer"]


def test_no_stage_means_no_stage_specific_advice():
    result = answer_case_question("What should I do next?", {})
    assert result["grounded"] is False
    assert "does not state the current stage" in result["answer"]
    assert result["next_steps"] == []


# ---------------------------------------------------------------------------
# GENERAL QUESTIONS — list what is known, name what is not
# ---------------------------------------------------------------------------

def test_general_question_lists_only_supplied_fields():
    result = _ask("Tell me about my case")
    assert result["grounded"] is True
    known = {item["value"] for item in result["known_case_facts"]}
    assert "CASE/2026/4471" in " ".join(known)
    assert "Pune Civil Court" in " ".join(known)

    # Every date-like token in the answer had to be in the context.
    context_tokens = set(re.findall(r"\d{1,2}[./-]\d{1,2}[./-]\d{4}", str(CONTEXT)))
    for token in re.findall(r"\d{1,2}[./-]\d{1,2}[./-]\d{4}", result["answer"]):
        assert token in context_tokens


def test_empty_context_says_there_is_nothing_to_answer_from():
    result = answer_case_question("Tell me about my case", {})
    assert result["grounded"] is False
    assert "No case information was supplied" in result["answer"]
    assert "case_context" in result["missing_information"]


def test_question_about_an_unknown_field_says_so_precisely():
    result = _ask("Who is the judge?")
    assert "judge" not in result["answer"].lower() or "does not state" in result["answer"]
    assert "does not state anything about the specific point" in result["answer"]


# ---------------------------------------------------------------------------
# NOTHING IS EVER INVENTED
# ---------------------------------------------------------------------------

def test_answers_never_carry_values_from_outside_the_context():
    sparse = {"case_number": "CASE/2026/4471"}
    questions = [
        "Why was the case adjourned?",
        "When is the next hearing?",
        "What is the status of my case?",
        "Explain the order.",
        "Who is the judge?",
        "What should I do next?",
    ]
    allowed = set(re.findall(r"\d+", str(sparse)))

    for question in questions:
        answer = answer_case_question(question, sparse)["answer"]
        for token in re.findall(r"\d+", answer):
            assert token in allowed, f"{question!r} invented {token}"


def test_context_that_is_not_a_dict_is_treated_as_absent():
    assert answer_case_question("When is the next hearing?", None)["grounded"] is False
    assert answer_case_question("When is the next hearing?", [])["grounded"] is False


def test_every_answer_carries_the_warnings_and_disclaimer():
    result = _ask("When is the next hearing?")
    assert any("only from the case information" in w for w in result["warnings"])
    assert result["disclaimer"]


# ---------------------------------------------------------------------------
# RESPONSE SHAPE — the case-workflow contract fields
# ---------------------------------------------------------------------------

def test_response_declares_the_case_mode_and_supporting_facts():
    result = _ask("What stage is my case at?")
    assert result["mode"] == "case"
    # The stage as the case information states it — not a stage
    # inferred from the question.
    assert result["current_stage"] == "Case adjourned for want of time"
    # `supporting_case_facts` is the documented alias of the facts the
    # answer was drawn from.
    assert result["supporting_case_facts"] == result["known_case_facts"]
    assert any(
        item["value"] == "CASE/2026/4471"
        for item in result["supporting_case_facts"]
    )


def test_current_stage_is_none_when_the_record_does_not_state_one():
    result = answer_case_question("What is the status of my case?", {})
    assert result["mode"] == "case"
    assert result["current_stage"] is None
    assert result["supporting_case_facts"] == []


# ---------------------------------------------------------------------------
# QUESTION ROUTING
# ---------------------------------------------------------------------------

def test_question_classification():
    assert classify_question("When is the next hearing?") == "next_hearing_date"
    assert classify_question("Next date of hearing") == "next_hearing_date"
    assert classify_question("Why was it adjourned?") == "adjournment_reason"
    assert classify_question("What stage is my case at?") == "current_stage"
    assert classify_question("What is the case status?") == "case_status"
    assert classify_question("Explain the order in simple words") == "order_explanation"
    assert classify_question("What should I do now?") == "what_to_do_next"
    assert classify_question("Who filed the petition?") == "general"
    assert classify_question("") == "general"

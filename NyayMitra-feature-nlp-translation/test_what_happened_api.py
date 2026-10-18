"""HTTP tests for the two "What Happened?" endpoints on the live NLP
service (default :8001):

    .venv/bin/pytest test_what_happened_api.py -v

    POST /api/incident/analyze   — what happened, read back hedged
    POST /api/case-companion/ask — a question about a case, answered
                                   only from the case information that
                                   came with it

Both are tested the way the frontend calls them: over HTTP, with the
same `Authorization: Bearer <NYAYMITRA_NLP_KEY>` convention as every
other endpoint on this service. The file also re-checks /api/guidance,
because that endpoint's scoring was moved into a shared module for
this feature and must keep behaving exactly as before.

The last test asks for a Hindi translation, which loads the en-indic
checkpoint — the same one /api/translate and /api/legal-simplify use,
under the same lock.
"""

from __future__ import annotations

import json
import os
import re
import time

import pytest
import requests

BASE = os.environ.get("NYAYMITRA_NLP_URL", "http://127.0.0.1:8001").rstrip("/")
API_KEY = os.environ.get("NYAYMITRA_NLP_KEY", "nyaymitra-local-test-2026")
HEADERS = {"Authorization": f"Bearer {API_KEY}"}
TIMEOUT = 600

ANALYSIS_KEYS = {
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
    "conversation_id",
    "language",
    "translated_response",
}

COMPANION_KEYS = {
    "mode",
    "question",
    "question_type",
    "answer",
    "grounded",
    "source",
    "current_stage",
    "known_case_facts",
    "supporting_case_facts",
    "next_steps",
    "simplified_order",
    "missing_information",
    "warnings",
    "answered_at",
    "disclaimer",
    "conversation_id",
    "language",
}

CASE_CONTEXT = {
    "case_number": "CASE/2026/4471",
    "court_name": "Pune Civil Court",
    "current_case_stage": "Case adjourned for want of time",
    "next_hearing_date": "15.10.2026",
    "case_history_timeline": [
        {
            "date": "22.09.2026",
            "event": "Adjourned",
            "description": "Matter adjourned to 15.10.2026.",
        }
    ],
    "orders": [
        {
            "date": "10.08.2026",
            "order_text": (
                "The petitioner is directed to file a written reply "
                "within four weeks from today."
            ),
        }
    ],
}


# ---------------------------------------------------------------------------
# FIXTURES
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def live_service():
    """Wait for the service rather than race it."""
    deadline = time.time() + 90
    last = "not started"

    while time.time() < deadline:
        try:
            response = requests.get(f"{BASE}/health", timeout=10)
            if response.ok:
                return
            last = f"status={response.status_code} {response.text[:120]}"
        except requests.RequestException as exc:
            last = str(exc)[:160]

        time.sleep(2)

    pytest.fail(
        f"NLP service is not reachable at {BASE} ({last}). "
        "Start it with: uvicorn translate_service:app --port 8001"
    )


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def analyze(payload: dict, auth: bool = True) -> requests.Response:
    return requests.post(
        f"{BASE}/api/incident/analyze",
        json=payload,
        headers=HEADERS if auth else {},
        timeout=TIMEOUT,
    )


def ask(payload: dict, auth: bool = True) -> requests.Response:
    return requests.post(
        f"{BASE}/api/case-companion/ask",
        json=payload,
        headers=HEADERS if auth else {},
        timeout=TIMEOUT,
    )


def _describe(response) -> str:
    return f"status={response.status_code} body={response.text[:300]}"


def _has_devanagari(text: str) -> bool:
    return any("ऀ" <= char <= "ॿ" for char in text)


# ---------------------------------------------------------------------------
# AUTH AND VALIDATION — the same contract as the rest of the service
# ---------------------------------------------------------------------------

def test_analyze_requires_the_api_key(live_service):
    response = analyze({"description": "something happened"}, auth=False)
    assert response.status_code == 401, _describe(response)


def test_ask_requires_the_api_key(live_service):
    response = ask({"question": "When is the next hearing?"}, auth=False)
    assert response.status_code == 401, _describe(response)


def test_analyze_refuses_an_empty_description(live_service):
    response = analyze({"description": "   "})
    assert response.status_code == 400, _describe(response)
    assert "Nothing to analyze" in response.json()["detail"]


def test_ask_refuses_an_empty_question(live_service):
    response = ask({"question": ""})
    assert response.status_code == 400, _describe(response)
    assert "Nothing to answer" in response.json()["detail"]


def test_unknown_target_language_is_rejected(live_service):
    response = analyze({"description": "hello", "target_lang": "fr_FR"})
    assert response.status_code == 400, _describe(response)
    assert "Unsupported target_lang" in response.json()["detail"]


# ---------------------------------------------------------------------------
# INCIDENT ANALYSIS
# ---------------------------------------------------------------------------

def test_analyze_contract(live_service):
    response = analyze({"description": "My bail application was rejected yesterday"})
    assert response.status_code == 200, _describe(response)
    body = response.json()
    assert set(body) == ANALYSIS_KEYS
    assert body["mode"] == "incident"
    assert body["original_input"] == "My bail application was rejected yesterday"
    assert body["confidence"]["level"] in {"low", "medium", "high"}
    assert body["language"] == "eng_Latn"
    assert body["conversation_id"]
    assert body["disclaimer"]
    assert isinstance(body["facts"], list)
    assert body["next_steps"]
    assert body["translated_response"]
    assert body["classification"]["source"] in {
        "none",
        "keyword_matching",
        "member2_model",
    }


def test_incident_endpoint_does_not_map_input_to_a_court_stage(live_service):
    """The input the old screen answered with "Notice issued to
    respondent" must come back as an incident reading."""
    body = analyze(
        {
            "description": (
                "I received a legal notice from the other side last "
                "week and do not know what to reply."
            )
        }
    ).json()
    rendered = json.dumps(body, ensure_ascii=False)

    assert body["mode"] == "incident"
    assert "guidance" not in body
    assert "Notice issued to respondent" not in rendered
    assert "court stage" not in body["possible_issue"].lower()
    assert "Based on what you described" in body["possible_issue"]


def test_urgency_is_never_a_fake_result(live_service):
    body = analyze({"description": "Someone threatened me and demanded money."}).json()
    urgency = body["urgency"]
    assert urgency["status"] == "not_available"
    assert "incident model is connected" in urgency["message"]
    # No band was computed, so no band may exist.
    assert "level" not in urgency
    assert body["classification"]["member2_connected"] in {True, False}


def test_vague_description_gets_the_agreed_low_confidence_warning(live_service):
    body = analyze({"description": "something happened"}).json()
    assert body["confidence"]["level"] == "low"
    assert (
        "More information is needed to understand this situation "
        "accurately."
    ) in body["warnings"]


def test_hedging_language_is_present(live_service):
    body = analyze({"description": "something happened"}).json()
    assert "Based on what you described" in body["possible_issue"]
    assert "not sufficient to determine" in body["possible_issue"]
    joined = " ".join(body["next_steps"])
    assert "You may consider" in joined


def test_detected_facts_come_from_the_description(live_service):
    description = (
        "On 15.10.2026 I paid Rs. 25,000 to Mr. Rahul Sharma by UPI "
        "transaction id TXN-889912 in Pune."
    )
    body = analyze({"description": description}).json()
    values = {fact["value"] for fact in body["facts"]}
    assert "15.10.2026" in values
    assert "Rs. 25,000" in values
    assert "TXN-889912" in values
    for fact in body["facts"]:
        if fact["source"] == "detected":
            assert fact["value"].lower() in description.lower()


def test_conversation_carries_facts_forward(live_service):
    first = analyze({"description": "I paid Rs. 5,000 on 15.10.2026."}).json()
    conversation_id = first["conversation_id"]
    assert any(f["value"] == "Rs. 5,000" for f in first["facts"])

    second = analyze(
        {"description": "and then nothing happened", "conversation_id": conversation_id}
    ).json()

    assert second["conversation_id"] == conversation_id
    # The second, vaguer turn still knows what the first one established.
    assert any(f["value"] == "Rs. 5,000" for f in second["facts"])
    assert second["confidence"]["level"] == "low"
    assert (
        "More information is needed to understand this situation accurately."
        in second["warnings"]
    )


def test_follow_up_is_read_together_with_the_prior_account(live_service):
    """"It happened yesterday" must be understood as referring to the
    incident described in the previous turn — the classic follow-up."""
    first = analyze(
        {
            "description": (
                "Someone called me pretending to be from my bank and "
                "asked for my OTP. After I gave it, money was deducted."
            )
        }
    ).json()

    second = analyze(
        {"description": "It happened yesterday.", "conversation_id": first["conversation_id"]}
    ).json()

    # The new message is echoed as sent...
    assert second["original_input"] == "It happened yesterday."
    # ...and the account it belongs to now carries both turns.
    assert "pretending to be from my bank" in second["what_user_described"]
    assert "It happened yesterday." in second["what_user_described"]
    # The follow-up answered the "when", so it is no longer missing.
    assert not any(
        "When did this happen" in q for q in second["missing_information"]
    )
    # The relative date counts as an established "when" — the basis
    # says so, and the reading still hedges about everything else.
    assert "when" in second["confidence"]["basis"]
    assert any(
        "based only on what you described" in w for w in second["warnings"]
    )


def test_knowledge_files_reported_honestly(live_service):
    body = analyze({"description": "something happened"}).json()
    assert set(body["knowledge"]["files"]) == {
        "categories",
        "next_steps",
        "questions",
        "facts",
    }
    if body["knowledge"]["source"] == "none":
        assert any("not loaded yet" in w for w in body["warnings"])


# ---------------------------------------------------------------------------
# CASE COMPANION
# ---------------------------------------------------------------------------

def test_ask_contract(live_service):
    response = ask(
        {"question": "When is the next hearing?", "case_context": CASE_CONTEXT}
    )
    assert response.status_code == 200, _describe(response)
    body = response.json()
    assert set(body) == COMPANION_KEYS
    assert body["mode"] == "case"
    assert body["question_type"] == "next_hearing_date"
    assert body["grounded"] is True
    assert "15.10.2026" in body["answer"]
    assert body["current_stage"] == "Case adjourned for want of time"
    assert body["supporting_case_facts"] == body["known_case_facts"]
    assert body["language"] == "eng_Latn"


def test_case_workflow_without_context_reports_no_stage(live_service):
    body = ask({"question": "What should I do next?"}).json()
    assert body["mode"] == "case"
    assert body["current_stage"] is None
    assert body["supporting_case_facts"] == []
    assert body["grounded"] is False


def test_absent_adjournment_reason_is_stated_as_absent(live_service):
    """The case the whole feature was named for."""
    body = ask(
        {"question": "Why was the case adjourned?", "case_context": CASE_CONTEXT}
    ).json()
    assert body["grounded"] is False
    assert (
        "The available case information does not state the reason for "
        "the adjournment."
    ) in body["answer"]
    assert "reason for the adjournment" in body["missing_information"]


def test_absent_status_is_stated_as_absent(live_service):
    body = ask(
        {"question": "What is the status of my case?", "case_context": CASE_CONTEXT}
    ).json()
    assert body["grounded"] is False
    assert (
        "The available case information does not state the status of "
        "the case."
    ) in body["answer"]


def test_present_stage_is_explained_with_the_existing_guidance(live_service):
    body = ask(
        {"question": "What stage is my case at?", "case_context": CASE_CONTEXT}
    ).json()
    assert body["grounded"] is True
    assert "Case adjourned for want of time" in body["answer"]
    assert body["next_steps"]
    assert "You may consider" in body["next_steps"][0]


def test_order_is_simplified_with_the_existing_engine(live_service):
    body = ask(
        {"question": "Explain the order.", "case_context": CASE_CONTEXT}
    ).json()
    assert body["grounded"] is True
    assert body["simplified_order"] is not None
    assert "must file" in body["simplified_order"]["simple_english"]


def test_empty_case_context_is_admitted(live_service):
    body = ask({"question": "Tell me about my case"}).json()
    assert body["grounded"] is False
    assert "No case information was supplied" in body["answer"]


def test_companion_conversation_is_recorded(live_service):
    body = ask(
        {"question": "When is the next hearing?", "case_context": CASE_CONTEXT}
    ).json()
    follow_up = ask(
        {"question": "And the status?", "conversation_id": body["conversation_id"]}
    ).json()
    assert follow_up["conversation_id"] == body["conversation_id"]


# ---------------------------------------------------------------------------
# REGRESSION — the endpoints this feature was built around
# ---------------------------------------------------------------------------

def test_guidance_endpoint_still_works_after_the_shared_scorer_move(live_service):
    response = requests.post(
        f"{BASE}/api/guidance",
        json={"text": "My bail application was rejected yesterday"},
        headers=HEADERS,
        timeout=60,
    )
    assert response.status_code == 200, _describe(response)
    body = response.json()
    assert body["matched"] is True
    assert body["stage"]
    assert body["what_to_do_next"]
    assert body["candidates"] == []


def test_guidance_endpoint_still_declines_a_match(live_service):
    response = requests.post(
        f"{BASE}/api/guidance",
        json={"text": "I want to open a shop in Pune"},
        headers=HEADERS,
        timeout=60,
    )
    assert response.status_code == 200, _describe(response)
    body = response.json()
    assert body["matched"] is False
    assert body["stage"] is None
    assert body["candidates"] == []


# ---------------------------------------------------------------------------
# SAFETY — nothing invented, nothing faked
# ---------------------------------------------------------------------------

def test_no_legal_section_is_invented(live_service):
    description = "Someone threatened me and demanded money from me."
    body = analyze({"description": description}).json()
    rendered = json.dumps(body, ensure_ascii=False)
    for match in re.findall(r"[Ss]ection\s+\d+[A-Z]?", rendered):
        assert match in description, f"invented {match}"


def test_no_hearing_date_is_invented(live_service):
    """A case with no next-hearing date must get none, ever."""
    body = ask(
        {
            "question": "When is the next hearing?",
            "case_context": {"case_number": "CASE/2026/4471"},
        }
    ).json()
    assert body["grounded"] is False
    for token in re.findall(r"\d{1,2}[./-]\d{1,2}[./-]\d{4}", body["answer"]):
        raise AssertionError(f"the answer invented a date: {token}")


def test_urgency_never_renders_as_a_computed_band(live_service):
    body = analyze({"description": "I was cheated out of Rs. 10,000."}).json()
    urgency = body["urgency"]
    assert urgency["status"] == "not_available"
    assert set(urgency) <= {
        "status",
        "message",
        "knowledge_indicators",
        "knowledge_indicator_note",
    }
    assert urgency.get("level") is None


# ---------------------------------------------------------------------------
# TRANSLATION — entities have to survive into Marathi/Hindi
# ---------------------------------------------------------------------------

def test_analyze_translates_and_preserves_the_date(live_service):
    body = analyze(
        {
            "description": "My bail application was rejected on 15.10.2026.",
            "target_lang": "hin_Deva",
        }
    ).json()

    assert body["language"] == "hin_Deva"
    assert _has_devanagari(body["possible_issue"])
    assert _has_devanagari(body["warnings"][0])
    # The date is restated by the simplification layer as
    # "15 October 2026" and must come back in that exact form, not
    # transliterated into Devanagari digits.
    assert "15 October 2026" in body["simple_explanation"]
    # The one-string rendering travels with it, sectioned and in the
    # requested language.
    assert body["translated_response"]
    assert _has_devanagari(body["translated_response"])
    assert "15 October 2026" in body["translated_response"]


def test_analyze_translates_to_marathi(live_service):
    body = analyze(
        {
            "description": "Someone threatened me and demanded money from me.",
            "target_lang": "mar_Deva",
        }
    ).json()

    assert body["language"] == "mar_Deva"
    assert _has_devanagari(body["simple_explanation"])
    assert _has_devanagari(body["translated_response"])
    # Translation never manufactures an urgency verdict on the way.
    assert body["urgency"]["status"] == "not_available"


def test_ask_translates_the_answer(live_service):
    body = ask(
        {
            "question": "When is the next hearing?",
            "case_context": CASE_CONTEXT,
            "target_lang": "mar_Deva",
        }
    ).json()

    assert body["language"] == "mar_Deva"
    assert _has_devanagari(body["answer"])
    # The hearing date is masked before the model sees it and restored
    # afterwards, so it comes back verbatim in the Marathi sentence.
    assert "15.10.2026" in body["answer"]


def test_identifiers_are_never_silently_lost_in_translation(live_service):
    """A case number or an amount must either survive into Hindi
    verbatim or be named in a warning — never disappear from both."""
    body = analyze(
        {
            "description": (
                "My case number is CASE/2026/4471 and I paid "
                "Rs. 25,000 on 15.10.2026."
            ),
            "target_lang": "hin_Deva",
        }
    ).json()

    assert body["language"] == "hin_Deva"

    # The date is restated by the simplification layer as
    # "15 October 2026" and has to come back in that exact form.
    assert "15 October 2026" in body["simple_explanation"]

    prose = " ".join(
        [body["simple_explanation"], body["possible_issue"]] + body["warnings"]
    )
    survived = "CASE/2026/4471" in prose
    flagged = any("CASE/2026/4471" in w for w in body["warnings"])
    assert survived or flagged, (
        "the case number vanished from both the translated prose and "
        "the warnings — a loss nobody would have been told about"
    )

    # The untranslated facts layer keeps every value verbatim, in
    # whichever script the rest of the answer was written.
    values = {fact["value"] for fact in body["facts"]}
    assert {"Rs. 25,000", "15.10.2026", "CASE/2026/4471"} <= values

    # And the sectioned summary carries the identifiers too — their own
    # words travel back untouched.
    assert "CASE/2026/4471" in body["translated_response"]
    assert _has_devanagari(body["translated_response"])

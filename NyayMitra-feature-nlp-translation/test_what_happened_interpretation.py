"""
The Member 2 interpretation seam for "What May Have Happened".

These tests pin the boundary the placeholder/model swap depends on:

  * unconnected model  -> rule-based placeholder, visibly marked
    (interpretation_source "placeholder_template" + PLACEHOLDER_HEDGE)
  * connected model    -> the model owns exactly the three reading
    fields, the hedge disappears, the source flips to "member2_model"
  * broken/invalid model -> graceful fallback to the placeholder; a
    bad model never breaks the answer
  * the payload sent to the model matches API_member2_interpretation.md
  * case mode is record-grounded and never consults the model
  * the private marker key never reaches the client

None of this touches voice, ASR or the frontend contract: the HTTP
shape of POST /api/what-happened is unchanged apart from the additive
`interpretation_source` field.
"""

import pytest

import what_happened_service as whs
from what_happened_interpretation import (
    MAX_HISTORY_TURNS,
    MODEL_URL_ENV,
    PLACEHOLDER_HEDGE,
    SOURCE_MODEL,
    SOURCE_PLACEHOLDER,
    SOURCE_RECORD,
    clear_interpreter,
    interpretation_status,
    model_payload,
    register_interpreter,
)

INCIDENT = "Someone threatened me and demanded money from me."

MODEL_READING = {
    "summary": "A possible cheating incident was described.",
    "possible_issue": (
        "Possible cheating — based only on what you described, and "
        "not a finding."
    ),
    "explanation": (
        "The model's own plain-words reading of the description."
    ),
}


@pytest.fixture(autouse=True)
def isolated_model(monkeypatch):
    """No model and no model URL unless a test wires one on purpose."""
    clear_interpreter()
    monkeypatch.delenv(MODEL_URL_ENV, raising=False)
    yield
    clear_interpreter()


def ask(text=INCIDENT, language="en", mode="incident", **extra):
    payload = {"mode": mode, "text": text, "language": language}
    payload.update(extra)
    return whs.handle_request(payload, store=whs.ConversationStore())


# ===========================================================================
# UNCONNECTED — the placeholder is clearly marked, never dressed up
# ===========================================================================

def test_placeholder_reading_is_marked_when_no_model_is_connected():
    response = ask()

    assert response["interpretation_source"] == SOURCE_PLACEHOLDER
    assert PLACEHOLDER_HEDGE in response["warnings"]

    status = interpretation_status()
    assert status["connected"] is False
    assert status["source"] == SOURCE_PLACEHOLDER


def test_empty_description_is_marked_as_placeholder_without_a_hedge():
    # No reading was rendered, so there is nothing to hedge against —
    # the "nothing was written" warning already says it all.
    response = ask(text="")

    assert response["interpretation_source"] == SOURCE_PLACEHOLDER
    assert PLACEHOLDER_HEDGE not in response["warnings"]
    assert response["summary"] == "No description was provided."


def test_an_unreachable_model_url_falls_back_to_the_placeholder(
    monkeypatch,
):
    monkeypatch.setenv(MODEL_URL_ENV, "http://127.0.0.1:9/interpret")

    response = ask()

    assert response["interpretation_source"] == SOURCE_PLACEHOLDER
    assert PLACEHOLDER_HEDGE in response["warnings"]
    assert response["summary"].strip()


# ===========================================================================
# CONNECTED — the model owns exactly the three reading fields
# ===========================================================================

def test_registered_model_owns_the_three_reading_fields():
    seen = {}

    def fake(text, language, history):
        seen.update({"text": text, "language": language, "history": history})
        return dict(MODEL_READING)

    register_interpreter(fake)
    response = ask()

    assert response["interpretation_source"] == SOURCE_MODEL
    assert response["summary"] == MODEL_READING["summary"]
    assert response["possible_issue"] == MODEL_READING["possible_issue"]
    assert response["explanation"] == MODEL_READING["explanation"]
    assert PLACEHOLDER_HEDGE not in response["warnings"]

    # Platform-owned fields stay platform-owned either way.
    assert response["next_steps"]
    assert response["preserve_information"]
    assert response["disclaimer"]

    # The documented inference payload, verbatim.
    assert seen["language"] == "en"
    assert INCIDENT in seen["text"]
    assert isinstance(seen["history"], list)

    # The private marker never reaches the client.
    assert "_model_fields" not in response


def test_status_flips_the_moment_a_model_is_registered():
    assert interpretation_status()["connected"] is False

    register_interpreter(lambda text, language, history: dict(MODEL_READING))

    status = interpretation_status()
    assert status["connected"] is True
    assert status["source"] == SOURCE_MODEL
    assert status["message"] == ""


def test_model_reading_passes_through_translation_verbatim():
    hindi = {
        "summary": "संभव छेड़छाड़ — केवल आपके वर्णन पर आधारित।",
        "possible_issue": "संभावित अपराध, केवल वर्णन के आधार पर।",
        "explanation": "मॉडल की अपनी व्याख्या, अनूदित नहीं की जाती।",
    }
    register_interpreter(lambda text, language, history: dict(hindi))
    translated = []

    def fake_translator(text, language):
        translated.append((text, language))
        return f"<{language}>{text}"

    response = whs.handle_request(
        {"mode": "incident", "text": INCIDENT, "language": "hi"},
        translator=fake_translator,
        store=whs.ConversationStore(),
    )

    # Model fields arrive in `language` and are passed through whole —
    # never re-translated (no "<hi>" wrapper around them).
    assert response["summary"] == hindi["summary"]
    assert response["possible_issue"] == hindi["possible_issue"]
    assert response["explanation"] == hindi["explanation"]

    # Platform fields were translated as usual.
    assert response["interpretation_source"] == SOURCE_MODEL
    assert any(lang == "hi" for _, lang in translated)
    assert any("<hi>" in step for step in response["next_steps"])


# ===========================================================================
# BROKEN / INVALID MODEL — graceful fallback, never a partial answer
# ===========================================================================

def test_a_broken_model_never_breaks_the_answer():
    def explode(text, language, history):
        raise RuntimeError("model is having a bad day")

    register_interpreter(explode)
    response = ask()

    assert response["interpretation_source"] == SOURCE_PLACEHOLDER
    assert PLACEHOLDER_HEDGE in response["warnings"]
    assert response["summary"].strip()
    assert response["next_steps"]


def test_an_incomplete_model_payload_is_rejected_not_partially_used():
    register_interpreter(
        lambda text, language, history: {"summary": "only a summary"}
    )
    response = ask()

    assert response["interpretation_source"] == SOURCE_PLACEHOLDER
    assert PLACEHOLDER_HEDGE in response["warnings"]
    assert response["summary"] != "only a summary"


# ===========================================================================
# THE CONTRACT ITSELF — what Member 2 receives and must return
# ===========================================================================

def test_the_inference_payload_matches_the_documented_contract():
    payload = model_payload("the description", "mr", ["first turn", " ", 42])

    assert set(payload) == {"text", "language", "history"}
    assert payload["text"] == "the description"
    assert payload["language"] == "mr"
    assert payload["history"] == ["first turn", "42"]


def test_history_sent_to_the_model_is_capped():
    many = [f"turn {index}" for index in range(20)]

    payload = model_payload("x", "en", many)

    assert len(payload["history"]) == MAX_HISTORY_TURNS
    assert payload["history"] == many[:MAX_HISTORY_TURNS]


# ===========================================================================
# CASE MODE — the record is read directly; no model is ever consulted
# ===========================================================================

def test_case_mode_is_record_grounded_not_a_model_reading():
    register_interpreter(lambda text, language, history: dict(MODEL_READING))

    response = ask(
        text="When is my next hearing?",
        mode="case",
        case_context={
            "case_number": "CASE/2026/4471",
            "next_hearing_date": "15.10.2026",
            "current_case_stage": "Case adjourned for want of time",
        },
    )

    assert response["interpretation_source"] == SOURCE_RECORD
    assert PLACEHOLDER_HEDGE not in response["warnings"]
    # The registered model was not used for the case answer.
    assert response["summary"] != MODEL_READING["summary"]

"""
Member 2's interpretation interface for "What May Have Happened" — an
adapter, not a model.

Member 2 will eventually provide the ML interpretation / generation
model that reads an incident description and says what may have
happened. Until that model arrives, `analyse_incident` in
`what_happened_service` produces the three reading fields from
rule-based templates. **That rule-based output is a placeholder, not
the final model output** — it must never be presented (or documented,
or demoed) as a trained model's verdict, and this module is what keeps
the two clearly apart:

    text + language + history  ->  interpret()  ->  reading or None

`interpret()` returns Member 2's reading when a model is connected and
None when it is not. The caller then either uses the model's three
fields (and flags the response `interpretation_source:
"member2_model"`) or keeps the placeholder and appends
`PLACEHOLDER_HEDGE` to the warnings (and flags the response
`interpretation_source: "placeholder_template"`). The placeholder
logic is never removed by this module; the model only ever sits on top
of it.

--------------------------------------------------------------------------
WHAT MEMBER 2'S MODEL MUST SEND BACK (the inference contract)
--------------------------------------------------------------------------

Request — exactly the JSON object this adapter POSTs (and the exact
argument triple it passes to a registered function):

    {
      "text": "Someone threatened me and demanded money from me.",
      "language": "hi",          // the language the USER will read:
                                 // "en" | "hi" | "mr"
      "history": ["...", "..."]   // earlier user turns, oldest
                                  // first, capped at MAX_HISTORY_TURNS
    }

Response — all three fields REQUIRED, every one a non-empty string:

    {
      "summary": "One-sentence lead of what may have happened.",
      "possible_issue": "The possible legal issue, hedged.",
      "explanation": "A plain-words explanation of that reading."
    }

Rules the response must obey:

  * Written in `language` — the platform passes these three fields
    through **verbatim** (they are never machine-translated again).
    Every *other* prose field in the API response is platform-owned
    English that the platform itself translates.
  * Each field capped at MAX_FIELD_CHARS characters (longer text is
    truncated by the adapter, not rejected).
  * Hedged wording only: "may", "appears to", "based on what you
    described". No invented sections, dates, deadlines, court
    outcomes or remedies — the platform's tests sweep the response
    for exactly that.
  * Extra keys are ignored by the adapter; missing, empty or
    non-string required fields reject the whole payload (the API then
    falls back to the placeholder).

Failure semantics: any exception, timeout, HTTP error or invalid
shape from the model yields None — the placeholder reading is used
and the response says so. A broken model never breaks the API.

--------------------------------------------------------------------------
CONNECTING MEMBER 2'S MODEL LATER (no frontend or endpoint changes)
--------------------------------------------------------------------------

In-process, at service startup:

    from what_happened_interpretation import register_interpreter
    register_interpreter(fn)   # fn(text, language, history) -> dict

or over HTTP without a redeploy, by setting:

    NYAYMITRA_WHAT_HAPPENED_MODEL_URL   POST the request JSON above
                                        -> the response JSON above

The moment a model is connected, `interpretation_status()` reports it
and responses produced from the model flag
`interpretation_source: "member2_model"`. Nothing else changes: the
HTTP contract of POST /api/what-happened, the frontend, and every
platform-owned field (next steps, preserve list, warnings, time
sensitivity, glossary, disclaimer) stay exactly as they are.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request

logger = logging.getLogger("nyaymitra.what_happened.interpretation")

MODEL_URL_ENV = "NYAYMITRA_WHAT_HAPPENED_MODEL_URL"

# The three fields the model owns. Everything else in the response is
# platform-owned and stays template/record-driven.
MODEL_FIELDS = ("summary", "possible_issue", "explanation")

# Private response key carrying WHICH fields the model produced, so
# `handle_request` can hand them to translate_response as
# `skip_fields` (already in the user's language — never re-translated).
# Popped before the response leaves the service.
MODEL_FIELDS_KEY = "_model_fields"

# `interpretation_source` values (machine-readable, never translated).
SOURCE_PLACEHOLDER = "placeholder_template"  # rule-based fallback in use
SOURCE_MODEL = "member2_model"               # Member 2's model produced it
SOURCE_RECORD = "record_grounded"            # case mode: read from the record

# Appended to the warnings whenever the placeholder produced the
# reading, so nobody reads it as the final model output. One source of
# truth: it disappears from responses the moment a valid model reading
# is used.
PLACEHOLDER_HEDGE = (
    "The “what may have happened” reading is a placeholder, not the "
    "final model output: the trained interpretation model is not "
    "connected yet, so this reading was produced by rule-based logic "
    "only."
)

NOT_CONNECTED_MESSAGE = (
    "The incident interpretation model is not connected yet."
)

MAX_FIELD_CHARS = 4000
MAX_HISTORY_TURNS = 6
HTTP_TIMEOUT_SECONDS = 10.0

# The registered model, if Member 2's code is wired in-process.
_INTERPRETER = None


def register_interpreter(fn) -> None:
    """Wire Member 2's model in-process.

    fn(text: str, language: str, history: list[str]) -> dict with the
    three required fields. Connection is process-global, exactly like
    `incident_classification.register_classifier`.
    """
    global _INTERPRETER
    _INTERPRETER = fn


def clear_interpreter() -> None:
    """Disconnect whatever was registered — for tests and restarts."""
    global _INTERPRETER
    _INTERPRETER = None


def model_payload(text: str, language: str = "en", history=()) -> dict:
    """Exactly the JSON object sent to Member 2's model."""
    turns = [
        str(turn).strip()
        for turn in list(history or ())[:MAX_HISTORY_TURNS]
        if str(turn).strip()
    ]
    return {
        "text": text or "",
        "language": language,
        "history": turns,
    }


def _normalize(candidate) -> dict | None:
    """Validate a model payload, or reject it outright.

    All three fields are required and must be non-empty strings; each
    is capped, not rejected, when long. Anything else — a partial
    payload, a wrong type, garbage — is treated as no answer at all.
    """
    if not isinstance(candidate, dict):
        return None

    reading = {}
    for field in MODEL_FIELDS:
        value = candidate.get(field)
        if not isinstance(value, str) or not value.strip():
            return None
        reading[field] = value.strip()[:MAX_FIELD_CHARS]
    return reading


def _http_call(url: str, payload: dict, timeout: float | None = None) -> object | None:
    try:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(
            request,
            timeout=timeout or HTTP_TIMEOUT_SECONDS,
        ) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        logger.warning("what-happened interpretation call failed: %s", exc)
        return None


def interpret(text: str, language: str = "en", history=()) -> dict | None:
    """Member 2's reading of this incident, or None when unavailable.

    Tries the registered model first, then
    `NYAYMITRA_WHAT_HAPPENED_MODEL_URL` if set. Any failure or invalid
    shape yields None — the caller then keeps the rule-based
    placeholder and says so in the warnings. No payload is ever
    synthesised: an absent model means an absent reading, not a
    defaulted one.
    """
    if _INTERPRETER is not None:
        try:
            candidate = _INTERPRETER(text, language, list(history or ()))
        except Exception:  # noqa: BLE001 - a broken model is "no answer"
            logger.exception("what-happened interpretation model raised")
            candidate = None
        validated = _normalize(candidate)
        if validated is not None:
            return validated

    url = os.environ.get(MODEL_URL_ENV, "").strip()
    if url:
        validated = _normalize(
            _http_call(url, model_payload(text, language, history)),
        )
        if validated is not None:
            return validated

    return None


def interpretation_status() -> dict:
    """Whether Member 2's model is connected — for tests and diagnostics."""
    connected = _INTERPRETER is not None or bool(
        os.environ.get(MODEL_URL_ENV, "").strip()
    )
    return {
        "connected": connected,
        "source": SOURCE_MODEL if connected else SOURCE_PLACEHOLDER,
        "message": "" if connected else NOT_CONNECTED_MESSAGE,
    }

"""
Member 2's incident-classification interface — an adapter, not a model.

Member 2 will eventually provide the ML classification / incident
understanding output for the "What Happened?" flow. Member 3 must
*consume* that output, never imitate it. This module is the documented
seam:

    text + language  ->  classify()  ->  classification payload or None

The payload Member 2's model is expected to return (all fields
optional, extra fields ignored):

    {
      "text": "...",                  # the text that was classified
      "language": "en",
      "intent": "incident",
      "incident_category": "...",     # the model's category id/label
      "confidence": 0.0,              # 0..1
      "facts": {"when": "..."},       # facts the model extracted
      "missing_information": ["..."]  # details the model found absent
    }

When no model is connected, `classify()` returns None and the
analysis falls back to keyword matching against Member 1's incident
knowledge files — and says so, in both `classification.source` and
the response warnings. No payload is ever synthesised: an absent
model means an absent classification, not a defaulted one.

Connecting Member 2's model later — either in-process:

    from incident_classification import register_classifier
    register_classifier(fn)   # fn(text, language) -> payload dict

or over HTTP without a redeploy, by setting:

    NYAYMITRA_INCIDENT_CLASSIFIER_URL   POST {"text": ..., "language": ...}
                                        -> classification payload JSON
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request

logger = logging.getLogger("nyaymitra.what_happened.classification")

CLASSIFIER_URL_ENV = "NYAYMITRA_INCIDENT_CLASSIFIER_URL"

NOT_CONNECTED_MESSAGE = (
    "The incident classification model is not connected yet; any "
    "category shown comes from keyword matching against the incident "
    "knowledge files, not from a trained model."
)

# Bounds on what a model payload may contribute. A model answer is
# data from outside this conversation, so it is validated and capped
# before it is allowed anywhere near the response.
MAX_FACTS = 30
MAX_MISSING = 10
MAX_VALUE_CHARS = 300

# The registered classifier, if Member 2's code is wired in-process.
_CLASSIFIER = None


def register_classifier(fn) -> None:
    """Register the classifier. `fn(text, language) -> payload dict`."""
    global _CLASSIFIER
    _CLASSIFIER = fn


def clear_classifier() -> None:
    """Disconnect whatever is registered (tests, and rollback)."""
    global _CLASSIFIER
    _CLASSIFIER = None


def _normalize(payload: object, fallback_text: str, language: str) -> dict | None:
    """A usable classification from a model answer, or None.

    Every field is validated and capped; missing fields become None /
    empty rather than being guessed at. A payload that carries no
    classification signal at all (no category, no confidence, no
    facts, no missing information) is treated as no answer — an empty
    dict must not make the response claim a model was consulted.
    """
    if not isinstance(payload, dict):
        return None

    text = payload.get("text")
    text = (
        text
        if isinstance(text, str) and text.strip()
        else fallback_text
    )

    lang = payload.get("language")
    lang = (
        lang
        if isinstance(lang, str) and lang.strip()
        else language
    )

    intent = payload.get("intent")
    intent = (
        intent
        if isinstance(intent, str) and intent.strip()
        else "incident"
    )

    category = payload.get("incident_category")
    category = (
        category.strip()
        if isinstance(category, str) and category.strip()
        else None
    )

    confidence = payload.get("confidence")
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not 0.0 <= float(confidence) <= 1.0
    ):
        confidence = None
    else:
        confidence = round(float(confidence), 4)

    facts: dict[str, str] = {}
    raw_facts = payload.get("facts")
    if isinstance(raw_facts, dict):
        for key, value in list(raw_facts.items())[:MAX_FACTS]:
            if value is None or isinstance(value, (dict, list)):
                continue
            rendered = str(value).strip()
            if rendered:
                facts[str(key)[:80]] = rendered[:MAX_VALUE_CHARS]

    missing: list[str] = []
    raw_missing = payload.get("missing_information")
    if isinstance(raw_missing, list):
        for item in raw_missing[:MAX_MISSING]:
            if isinstance(item, str) and item.strip():
                missing.append(item.strip()[:MAX_VALUE_CHARS])

    if category is None and confidence is None and not facts and not missing:
        return None  # nothing was actually classified

    return {
        "text": text,
        "language": lang,
        "intent": intent,
        "incident_category": category,
        "confidence": confidence,
        "facts": facts,
        "missing_information": missing,
    }


def _http_call(url: str, payload: dict, timeout: float = 4.0) -> object | None:
    try:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        logger.warning("incident classifier call failed: %s", exc)
        return None


def classify(text: str, language: str = "en") -> dict | None:
    """Member 2's classification of this text, or None when unconnected.

    Tries the registered classifier first, then
    `NYAYMITRA_INCIDENT_CLASSIFIER_URL` if set. Any failure or invalid
    shape yields None — the caller then falls back to keyword matching
    and reports the source honestly.
    """
    if _CLASSIFIER is not None:
        try:
            candidate = _CLASSIFIER(text, language)
        except Exception:  # noqa: BLE001 - a broken model is "no answer"
            logger.exception("incident classifier raised")
            candidate = None
        validated = _normalize(candidate, text, language)
        if validated is not None:
            return validated

    url = os.environ.get(CLASSIFIER_URL_ENV, "").strip()
    if url:
        validated = _normalize(
            _http_call(url, {"text": text, "language": language}),
            text,
            language,
        )
        if validated is not None:
            return validated

    return None


def classifier_status() -> dict:
    """Whether Member 2's model is connected — for API responses/tests."""
    connected = _CLASSIFIER is not None or bool(
        os.environ.get(CLASSIFIER_URL_ENV, "").strip()
    )
    return {
        "connected": connected,
        "source": "member2_model" if connected else "not_connected",
        "message": "" if connected else NOT_CONNECTED_MESSAGE,
    }

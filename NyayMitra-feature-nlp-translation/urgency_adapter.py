"""
Urgency interface for the incident workflow — an adapter, not a model.

The "What Happened?" flow has a place where a judgment about how
urgent an incident is belongs (the response's `urgency` field). That
judgment must come from Member 2's incident/urgency model. This module
is the seam it plugs into:

    incident input  ->  assess_urgency()  ->  urgency result

While no model is connected, every call returns exactly:

    {"status": "not_available",
     "message": "Incident urgency analysis will be provided when the
                 incident model is connected."}

Nothing in this module — or anywhere downstream of it — ever produces
a LOW/MEDIUM/HIGH band of its own. A stage-lookup band, a keyword
score or a hand-written constant is not an assessment of *this*
incident, and showing one as though a model produced it would be a
fabrication. The result shape is deliberately explicit about that:
`status` is either "not_available" or "available", and `level` only
exists in the second case.

Connecting Member 2's model later — either in-process:

    from urgency_adapter import register_urgency_model
    register_urgency_model(fn)   # fn(text, classification) -> dict

or over HTTP without a redeploy, by setting:

    NYAYMITRA_URGENCY_MODEL_URL   POST {"text": ..., "intent": "incident"}
                                  -> urgency result JSON

A model answer is accepted only if it validates against the shape
documented in `_validated`. Anything else (garbage, a partial answer,
an unknown level) degrades to `not_available` — never to a guess.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request

logger = logging.getLogger("nyaymitra.what_happened.urgency")

URGENCY_MODEL_URL_ENV = "NYAYMITRA_URGENCY_MODEL_URL"

NOT_CONNECTED_MESSAGE = (
    "Incident urgency analysis will be provided when the incident "
    "model is connected."
)

# The only answer given while no model is connected.
NOT_AVAILABLE_RESULT = {
    "status": "not_available",
    "message": NOT_CONNECTED_MESSAGE,
}

_LEVELS = {"low", "medium", "high"}

# The registered model, if Member 2's code is wired in-process.
_MODEL = None


def register_urgency_model(fn) -> None:
    """Register the urgency model. `fn(text, classification) -> dict`."""
    global _MODEL
    _MODEL = fn


def clear_urgency_model() -> None:
    """Disconnect whatever is registered (tests, and rollback)."""
    global _MODEL
    _MODEL = None


def _validated(candidate: object) -> dict | None:
    """A model answer in the documented shape, or None.

    Strict on purpose: a half-answer ("available" with no level, a
    level we do not know) is treated as no answer at all, because a
    half-shaped urgency result is exactly how a fake-looking band
    would sneak into the UI.
    """
    if not isinstance(candidate, dict):
        return None

    status = candidate.get("status")
    if status == "not_available":
        message = candidate.get("message")
        return {
            "status": "not_available",
            "message": (
                message
                if isinstance(message, str) and message.strip()
                else NOT_CONNECTED_MESSAGE
            ),
        }
    if status != "available":
        return None

    level = candidate.get("level")
    if level not in _LEVELS:
        return None

    message = candidate.get("message")
    result = {
        "status": "available",
        "level": level,
        "message": (
            message.strip()
            if isinstance(message, str) and message.strip()
            else ""
        ),
        "source": "incident-urgency-model",
    }
    basis = candidate.get("basis")
    if isinstance(basis, str) and basis.strip():
        result["basis"] = basis.strip()
    return result


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
        logger.warning("urgency model call failed: %s", exc)
        return None


def assess_urgency(text: str, classification: dict | None = None) -> dict:
    """The urgency of this incident — from the model, or not at all.

    Tries the registered model first, then `NYAYMITRA_URGENCY_MODEL_URL`
    if set. Any failure, absence or invalid shape yields
    `NOT_AVAILABLE_RESULT`, so the caller can render the honest
    "not connected" state instead of a band nobody computed.
    """
    candidate: object = None

    if _MODEL is not None:
        try:
            candidate = _MODEL(text, classification)
        except Exception:  # noqa: BLE001 - a broken model is "not available"
            logger.exception("urgency model raised")

    if candidate is None:
        url = os.environ.get(URGENCY_MODEL_URL_ENV, "").strip()
        if url:
            candidate = _http_call(
                url,
                {
                    "text": text,
                    "intent": "incident",
                    "category": (classification or {}).get("incident_category"),
                },
            )

    return _validated(candidate) or dict(NOT_AVAILABLE_RESULT)


def urgency_status() -> dict:
    """Whether an urgency model is connected — for API responses/tests."""
    connected = _MODEL is not None or bool(
        os.environ.get(URGENCY_MODEL_URL_ENV, "").strip()
    )
    return {
        "connected": connected,
        "source": "incident-urgency-model" if connected else "not_connected",
        "message": "" if connected else NOT_CONNECTED_MESSAGE,
    }

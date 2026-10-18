"""
Unified "Tell Us What Happened" pipeline.

    user text -> validate -> intent -> (incident category + facts + missing)
              -> structured JSON for Member 3's NLP / legal-explanation layer

process_user_input(text) is the single entry point exposed by the API
(POST /understand-situation).

Output shape (Member 1's spec, plus `category_id` and `message` added on
request):

    {
      "intent": "incident",                       # lower-cased intent, or
                                                  # "unclear"
      "incident_category": "online_financial_...", # snake_case slug or null
      "category_id": "INC001",                     # category id or null
      "confidence": 0.91,                          # category score for
                                                   # incidents, intent score
                                                   # otherwise
      "facts": {"amount": "5000", ...} or null,
      "missing_information": ["transaction_date", ...] or null,
      "message": "Please rephrase..." or null
    }

For CASE_QUESTION / FOLLOW_UP the category/category_id/facts/missing fields are
null - those inputs go to Member 3's case-data lookup instead of incident
analysis.

Confidence threshold: whenever the score that decided the output (the incident
category score for INCIDENT, the intent score otherwise) is below
CONFIDENCE_THRESHOLD, the pipeline returns intent "unclear" with a `message`
asking the user to rephrase, and no category / facts / missing information.
The constant is the single place to tune that cut-off.

Margin guard: MARGIN_THRESHOLD is a second, independent cut-off on the gap
between the winning intent class and the runner-up class at the intent stage
(best neighbour of the winner minus best neighbour of any other label). Input
whose two leading classes are neck and neck - gibberish, greetings,
chit-chat, a question phrased like an incident - is refused even when its
confidence looks acceptable. 0.00 turns the rule off.

Note: fact keys are the exact `fact_or_entity` names from
data/raw/incident_facts.json (that file has no "payment_method" style keys;
its name for that fact is "bank/wallet/payment method"), and
`incident_category` is the slug of `category_name` - use
incident_classifier.resolve_category(slug) to get the full record back.
"""

from __future__ import annotations

import time

from fact_extractor import extract_facts
from incident_classifier import category_slug, classify_incident_category
from intent_classifier import INCIDENT, classify_intent_detailed
from missing_info import get_missing_info
from sentence_encoder import MODEL_NAME
from text_validation import validate_user_input

# Minimum confidence before the pipeline answers instead of guessing.
# The score compared is the one that decided the output: the incident category
# score for INCIDENT, the intent score for CASE_QUESTION / FOLLOW_UP.
# Single place to tune the cut-off.
#
# 0.35 comes from the held-out calibration in src/evaluate_intent.py: the
# HIGHEST confidence among the 15 out-of-scope inputs (greetings, gibberish,
# cooking, weather, sports, chit-chat) is 0.341, so 0.35 is the lowest round
# cut-off that refuses every one of them. It also answers more correct rows
# than the old 0.45 (42 vs 33 of 53, before the margin guard).
CONFIDENCE_THRESHOLD = 0.35

# Minimum gap between the winning class and the runner-up class at the intent
# stage (best neighbour of the winner minus best neighbour of any other
# label - classify_intent_detailed()["label_margin"]). 0.00 disables the
# rule; both guards must hold for the pipeline to answer.
#
# 0.16 from the same calibration: the HIGHEST such gap among the 7 wrong
# held-out answers is 0.116 and among the 15 out-of-scope inputs is 0.157, so
# 0.16 refuses all wrong answers (including the two confident Hindi mistakes
# at confidence 0.814 / 0.743, which no confidence cut-off can catch) and -
# independently of CONFIDENCE_THRESHOLD - also refuses every out-of-scope
# input.
#
# Note: the guard deliberately uses the class gap, not top1 minus top2 of the
# raw neighbours. Two near-duplicate examples of the same class sit close
# together, so a plain top1-top2 rule refuses obvious answers (an input with
# confidence 0.805 whose two nearest neighbours are both CASE_QUESTION scores
# only 0.053). Evaluated on the 60 held-out rows the two rules keep 34 vs 25
# correct answers, and both leak 0 wrong / 0 out-of-scope.
#
# Together the constants answer 34 of 53 correct held-out rows (the other 19
# become "unclear"), 0 wrong, 0 out-of-scope - against 33 correct / 3 wrong /
# 0 out-of-scope for the previous confidence-only guard at 0.45.
MARGIN_THRESHOLD = 0.16

# Shown when a guard rejects the answer.
UNCLEAR_MESSAGE = (
    "I could not understand that confidently. Please rephrase your message "
    "or add a few more details about what happened."
)


def _mark_unclear(result: dict, reason: str = None) -> dict:
    """Downgrade a low-confidence answer: intent "unclear", no category, no
    facts, and a message asking the user to rephrase.

    `reason` is a short human-readable note about which guard fired
    (confidence, margin, or both).
    """
    result["intent"] = "unclear"
    result["incident_category"] = None
    result["category_id"] = None
    result["facts"] = None
    result["missing_information"] = None
    detail = reason or (
        f"confidence {result['confidence']:.2f} is below "
        f"the {CONFIDENCE_THRESHOLD} threshold"
    )
    result["message"] = f"{UNCLEAR_MESSAGE} ({detail})"
    return result


def process_user_input(text: str) -> dict:
    """Run the full understanding pipeline on one free-text input.

    Raises ValueError when the input is empty / not a string (the API turns
    that into an HTTP 400).
    """
    cleaned = validate_user_input(text)              # 1. shared validation
    intent_result = classify_intent_detailed(cleaned)  # 2. intent (+ margin)

    intent = intent_result["intent"]
    intent_confidence = intent_result["confidence"]
    intent_gap = intent_result["label_margin"]
    result = {
        "intent": intent.lower(),
        "incident_category": None,
        "category_id": None,
        "confidence": intent_confidence,
        "facts": None,
        "missing_information": None,
        "message": None,
    }

    # Margin guard, measured at the intent stage: if the runner-up class is
    # almost as close as the winner, the input is ambiguous (gibberish,
    # greetings, a case question phrased like an incident), so neither branch
    # below may answer. Applies to all three intents.
    if intent_gap < MARGIN_THRESHOLD:
        return _mark_unclear(
            result,
            f"gap {intent_gap:.2f} to the runner-up intent is below the "
            f"{MARGIN_THRESHOLD} margin threshold",
        )

    if intent != INCIDENT:                       # 4. case question / follow-up
        if result["confidence"] < CONFIDENCE_THRESHOLD:
            return _mark_unclear(result)
        return result

    # 3. incident-only branch: category, facts, missing information
    category = classify_incident_category(cleaned, top_k=3)
    result["confidence"] = category["confidence"]
    if category["confidence"] < CONFIDENCE_THRESHOLD:
        # Too unsure about the category - answer nothing rather than guess.
        return _mark_unclear(result)

    facts = extract_facts(cleaned, category["category_id"])
    missing = get_missing_info(category["category_id"], facts)

    result["incident_category"] = category_slug(category["category_name"])
    result["category_id"] = category["category_id"]
    result["facts"] = facts
    result["missing_information"] = missing
    return result


def warm_up() -> dict:
    """Load everything /understand-situation needs, before the first request.

    Importing this module already reads the JSON data files and the cached
    embedding matrices (models/intent_embeddings.npz and
    models/incident_category_embeddings.npz). What is left is the
    sentence-transformers encoder itself, so this runs one throw-away
    classification end-to-end: after it, the first real request does not pay
    the model-load cost.

    Called from the API startup hook; never raises into the request path -
    if it fails, /understand-situation still works, only slower, and
    /predict-delay is unaffected either way.
    """
    started = time.time()
    classify_intent_detailed("warm up")
    classify_incident_category("warm up")
    return {
        "encoder": MODEL_NAME,
        "loaded": True,
        "seconds": round(time.time() - started, 3),
    }

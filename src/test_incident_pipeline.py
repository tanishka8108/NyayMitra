"""
End-to-end test for the "Tell Us What Happened" ML layer.

Run from the src/ directory:

    python test_incident_pipeline.py

Coverage (12 inputs):
  * 4 clear incidents from 4 different categories (INC001 / INC016 / INC017 /
    INC021) - full JSON output incl. facts + missing information,
  * 3 case-question style inputs - category/facts/missing must be null,
  * 3 follow-up style inputs - category/facts/missing must be null,
  * 1 empty string - must be rejected cleanly with ValueError,
  * 1 gibberish string - must not crash and must come back with a low
    confidence.

Note: the CASE_QUESTION / FOLLOW_UP training examples are synthetic and still
await team review (see the _meta header of resources/intent_examples.json), so
the two non-incident classes are the least trustworthy part of this run.
"""

from __future__ import annotations

import json
import time
import traceback

from incident_pipeline import (
    CONFIDENCE_THRESHOLD,
    MARGIN_THRESHOLD,
    process_user_input,
)
from intent_classifier import classify_intent_detailed

CASES = [
    # --- 4 clear incidents, different categories ---------------------------
    {
        "label": "incident / financial fraud",
        "expected_intent": "incident",
        "expected_category_slug": "online_financial_fraud_unauthorized_digital_transaction",
        "expected_category_id": "INC001",
        "text": (
            "Rs 5,000 was debited from my savings account through UPI on "
            "14 September 2026 without my permission. The transaction reference "
            "number is 81234567 and I have downloaded the bank statement."
        ),
    },
    {
        "label": "incident / landlord deposit",
        "expected_intent": "incident",
        "expected_category_slug": "landlord_tenant_lease_dispute",
        "expected_category_id": "INC016",
        "text": (
            "My landlord is not returning my security deposit of Rs 20,000 even "
            "though the rental agreement ended last month and I vacated the house."
        ),
    },
    {
        "label": "incident / unpaid salary",
        "expected_intent": "incident",
        "expected_category_slug": "wages_salary_employment_payment_issue",
        "expected_category_id": "INC017",
        "text": (
            "My employer has not paid my salary of 45,000 rupees for the last "
            "two months despite repeated reminders."
        ),
    },
    {
        "label": "incident / road accident",
        "expected_intent": "incident",
        "expected_category_slug": "motor_vehicle_accident_road_incident",
        "expected_category_id": "INC021",
        "text": (
            "A two-wheeler came from the wrong side and rammed into my car near "
            "the market on 12/08/2026. My car is badly damaged and I have an FIR copy."
        ),
    },
    # --- 3 case questions ---------------------------------------------------
    {
        "label": "case question / adjourned hearing",
        "expected_intent": "case_question",
        "text": (
            "The hearing in my case happened today and the judge adjourned the "
            "matter, what should I do now?"
        ),
    },
    {
        "label": "case question / stage meaning",
        "expected_intent": "case_question",
        "text": "What does the arguments stage mean for my case?",
    },
    {
        "label": "case question / delay",
        "expected_intent": "case_question",
        "text": "Why is my case taking so long to get a final judgment?",
    },
    # --- 3 follow-ups -------------------------------------------------------
    {
        "label": "follow-up / reference number (below threshold -> unclear)",
        "expected_intent": "unclear",
        "text": "What about the reference number?",
    },
    {
        "label": "follow-up / lawyer",
        "expected_intent": "follow_up",
        "text": "Will I need a lawyer for this?",
    },
    {
        "label": "follow-up / seriousness",
        "expected_intent": "follow_up",
        "text": "Is that a serious problem?",
    },
    # --- edge cases ---------------------------------------------------------
    {
        "label": "empty string (must be rejected cleanly)",
        "expected_error": True,
        "text": "",
    },
    {
        "label": "gibberish (low confidence, must not crash)",
        "expected_intent": "any",
        "max_confidence": 0.30,
        "text": "xq9#vZ!pla?42 42 42 asdfghjkl;qwerty",
    },
]

OUTPUT_KEYS = [
    "intent",
    "incident_category",
    "category_id",
    "confidence",
    "facts",
    "missing_information",
    "message",
]


def run() -> int:
    failures = []

    for index, case in enumerate(CASES, start=1):
        print("=" * 100)
        print(f"[{index:02d}] {case['label']}")
        print(f"     input: {case['text']!r}")
        print("-" * 100)

        start = time.time()
        try:
            result = process_user_input(case["text"])
        except ValueError as exc:
            elapsed = time.time() - start
            print(f"     REJECTED CLEANLY after {elapsed:.2f}s -> ValueError: {exc}")
            if not case.get("expected_error"):
                failures.append(f"{case['label']}: unexpected ValueError ({exc})")
            continue
        except Exception:
            print("     CRASHED:")
            traceback.print_exc()
            failures.append(f"{case['label']}: crashed")
            continue

        print(json.dumps(result, indent=2, ensure_ascii=False))
        print(f"     ({time.time() - start:.2f}s)")

        # --- structural assertions -----------------------------------------
        if list(result.keys()) != OUTPUT_KEYS:
            failures.append(f"{case['label']}: unexpected keys {list(result.keys())}")
        if not isinstance(result["confidence"], (int, float)) or not (
            0.0 <= result["confidence"] <= 1.0
        ):
            failures.append(f"{case['label']}: confidence out of range")

        expected_intent = case.get("expected_intent")
        if expected_intent == "any":
            if result["confidence"] > case.get("max_confidence", 1.0):
                failures.append(
                    f"{case['label']}: confidence {result['confidence']} not low"
                )
        elif expected_intent and result["intent"] != expected_intent:
            failures.append(
                f"{case['label']}: intent {result['intent']} != {expected_intent}"
            )

        # The guard contract: intent is "unclear" exactly when the answer was
        # refused - by the confidence guard (the returned score, which is the
        # category score for incidents) or by the margin guard (gap between
        # the winning intent class and the runner-up) - and then a rephrase
        # message is set.
        gap = classify_intent_detailed(case["text"])["label_margin"]
        is_unclear = result["intent"] == "unclear"
        refused = (
            result["confidence"] < CONFIDENCE_THRESHOLD
            or gap < MARGIN_THRESHOLD
        )
        if is_unclear != refused:
            failures.append(
                f"{case['label']}: unclear={is_unclear} but confidence "
                f"{result['confidence']} vs {CONFIDENCE_THRESHOLD} and gap "
                f"{gap} vs {MARGIN_THRESHOLD}"
            )
        if is_unclear and not result["message"]:
            failures.append(f"{case['label']}: unclear without a message")
        if not is_unclear and result["message"] is not None:
            failures.append(f"{case['label']}: message set although not unclear")

        if case.get("expected_category_slug") and (
            result["incident_category"] != case["expected_category_slug"]
        ):
            failures.append(
                f"{case['label']}: category {result['incident_category']} != "
                f"{case['expected_category_slug']}"
            )

        if case.get("expected_category_id") and (
            result["category_id"] != case["expected_category_id"]
        ):
            failures.append(
                f"{case['label']}: category_id {result['category_id']} != "
                f"{case['expected_category_id']}"
            )

        # Non-incident inputs must leave the incident-only fields null.
        if result["intent"] != "incident":
            for key in ("incident_category", "category_id", "facts",
                        "missing_information"):
                if result[key] is not None:
                    failures.append(f"{case['label']}: {key} should be null")
        else:
            if not isinstance(result["facts"], dict):
                failures.append(f"{case['label']}: facts should be a dict")
            if not isinstance(result["missing_information"], list):
                failures.append(f"{case['label']}: missing_information should be a list")

    print("=" * 100)
    if failures:
        print(f"RESULT: {len(failures)} FAILURE(S)")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("RESULT: all checks passed "
          "(12 inputs: 4 incidents, 3 case questions, 3 follow-ups, "
          "1 empty, 1 gibberish)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())

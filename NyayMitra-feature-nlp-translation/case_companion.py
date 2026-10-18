"""
Case companion — grounded answers about a *supplied* case.

`POST /api/case-companion/ask` receives a question and the case
information Member 4's My Cases work supplies with it (case number,
stage, timeline, orders, hearing dates …). This module answers only
from that information.

The rule it is built around: say what is not there. If the question
asks why the matter was adjourned and the case information does not
carry a reason, the answer is

    "The available case information does not state the reason for the
    adjournment."

— not a plausible-sounding reason. Nothing here searches for, infers
or completes a date, a status, a party or a justification. The only
thing it may add beyond the raw fields is (a) plain-English rewriting
of order text that *is* present, through the existing
`legal_simplification` engine, and (b) the existing case-stage
guidance, when the stage is stated in the case information and the
question asks what that stage calls for.

Accepted `case_context` shape (all keys optional, aliases accepted —
the loader is deliberately forgiving because Member 4's exact shapes
are still moving):

    case_number / case_no / filing_number / caseNo
    cnr / cnr_number
    court_name / court
    current_case_stage / case_stage / stage
    case_status / status
    next_hearing_date / next_date / next_date_of_hearing / hearing_date
    parties / petitioner / petitioner_name / respondent / respondent_name
    case_type / category
    timeline / case_history_timeline / events / history / proceedings
        list of dicts (date, event, description, …) or list of strings
    orders / court_orders / order_history
        list of dicts (title, date, text/order_text/summary, …)
    order_text / latest_order_text / document_text
        the text of one order, as a string

Unknown keys are ignored; a wrongly-typed value is treated as absent.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from guidance_matching import match_guidance
from legal_simplification import simplify_legal_text
from next_steps_guidance_lookup import load_guidance_data

# Field name -> how it is labelled when shown back to the reader.
FIELD_LABELS: list[tuple[str, str, tuple[str, ...]]] = [
    ("case_number", "case number",
     ("case_number", "case_no", "caseNo", "filing_number", "number")),
    ("cnr", "CNR", ("cnr", "cnr_number", "cnrNo")),
    ("court", "court", ("court_name", "court", "courtName", "court_name_en")),
    ("case_stage", "current stage",
     ("current_case_stage", "case_stage", "stage", "present_stage")),
    ("status", "status", ("case_status", "status", "status_text")),
    ("next_hearing_date", "next hearing date",
     ("next_hearing_date", "next_date", "nextDate",
      "next_date_of_hearing", "hearing_date", "next_hearing")),
    ("case_type", "case type", ("case_type", "category", "case_category")),
    ("petitioner", "petitioner",
     ("petitioner", "petitioner_name", "petitionerName", "plaintiff")),
    ("respondent", "respondent",
     ("respondent", "respondent_name", "respondentName", "defendant")),
]

TIMELINE_KEYS = ("timeline", "case_history_timeline", "events",
                 "history", "proceedings")
ORDER_LIST_KEYS = ("orders", "court_orders", "order_history")
ORDER_TEXT_KEYS = ("order_text", "latest_order_text", "document_text",
                   "latest_order", "order")

# Phrases that turn "the matter was adjourned" into "…and here is why".
_REASON_MARKERS = re.compile(
    r"\b(for want of|because|since|due to|on account of|at the request|"
    r"on the request|request of|in the absence|absence of|"
    r"non-availability|not available|unable to|awaiting|pending receipt|"
    r"till the (?:record|file)|overgrown|on account)\b",
    re.IGNORECASE,
)

_NOT_STATED = "The available case information does not state the"

STANDING_WARNING = (
    "This answer is drawn only from the case information supplied "
    "with the question. Nothing beyond it has been assumed."
)

UNCOVERED_WARNING = (
    "The supplied case information does not cover this question."
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clean_context(case_context: dict | None) -> dict:
    if isinstance(case_context, dict):
        return case_context
    return {}


def _lookup(context: dict, aliases: tuple[str, ...]) -> tuple[str, object] | None:
    """(key, value) for the first alias that is present and not blank."""
    for alias in aliases:
        if alias not in context:
            continue
        value = context[alias]
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, (list, dict)) and not value:
            continue
        return alias, value
    return None


def _scalar(value: object) -> str | None:
    """A displayable string out of a field, or None if it is not one."""
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, list):
        parts = [item for item in (_scalar(v) for v in value) if item]
        return "; ".join(parts) or None
    if isinstance(value, dict):
        parts = [
            f"{key}: {text}"
            for key, item in value.items()
            if (text := _scalar(item))
        ]
        return "; ".join(parts) or None
    return None


def _entry_text(entry: object) -> str:
    """One timeline/order entry as a readable sentence."""
    if isinstance(entry, str):
        return entry.strip()
    if not isinstance(entry, dict):
        return _scalar(entry) or ""

    preferred = (
        "event", "title", "description", "order_text", "order_details",
        "text", "detail", "summary", "proceedings", "order", "observation",
        "remarks", "purpose_of_hearing",
    )
    parts: list[str] = []
    for key in preferred:
        text = _scalar(entry.get(key))
        if text:
            parts.append(text)
    if not parts:
        parts = [
            f"{key}: {text}"
            for key, item in entry.items()
            if (text := _scalar(item))
        ]
    date = _scalar(
        entry.get("date")
        or entry.get("order_date")
        or entry.get("hearing_date")
        or entry.get("business_on_date")
    )
    if date and date not in parts:
        parts.insert(0, date)
    return " — ".join(parts)


def _list_field(context: dict, keys: tuple[str, ...]) -> tuple[str, list] | None:
    found = _lookup(context, keys)
    if not found:
        return None
    key, value = found
    if isinstance(value, list):
        return key, value
    return key, [value]


def _all_texts(context: dict) -> list[tuple[str, str]]:
    """(where, text) pairs for everything readable in the context.

    Narrative entries come first: when someone asks why the matter was
    adjourned, the timeline's own words are a better thing to quote
    than the stage label on the header row. Used only for *finding
    whether something is mentioned* — never as a source of new facts.
    """
    out: list[tuple[str, str]] = []
    for keys in (TIMELINE_KEYS, ORDER_LIST_KEYS):
        listing = _list_field(context, keys)
        if listing:
            key, entries = listing
            for index, entry in enumerate(entries):
                text = _entry_text(entry)
                if text:
                    out.append((f"{key}[{index}]", text))
    for key in ORDER_TEXT_KEYS:
        if isinstance(context.get(key), str) and context[key].strip():
            out.append((key, context[key].strip()))
    for field, _label, aliases in FIELD_LABELS:
        found = _lookup(context, aliases)
        if found:
            text = _scalar(found[1])
            if text:
                out.append((found[0], text))
    return out


def classify_question(question: str) -> str:
    """Which of the supported questions this one is. "general" otherwise."""
    q = " ".join(question.lower().split())
    if not q:
        return "general"

    explain_words = ("explain", "meaning", "mean", "simplify", "plain",
                     "in simple", "what does it say", "what does the order say",
                     "read", "translate")

    if ("next hearing" in q) or ("next date" in q) or ("date of next" in q) or (
        "when" in q and ("hearing" in q or "court date" in q or "sitting" in q)
    ):
        return "next_hearing_date"
    if "adjourn" in q:
        return "adjournment_reason"
    if "stage" in q:
        return "current_stage"
    if "status" in q or "what is happening" in q or "how is my case" in q:
        return "case_status"
    if ("order" in q or "judgment" in q or "judgement" in q) and any(
        word in q for word in explain_words
    ):
        return "order_explanation"
    if any(phrase in q for phrase in
           ("what should i do", "next step", "now what", "what can i do",
            "what to do")):
        return "what_to_do_next"
    return "general"


def _known_facts(context: dict) -> list[dict]:
    known: list[dict] = []
    for field, label, aliases in FIELD_LABELS:
        found = _lookup(context, aliases)
        if not found:
            continue
        text = _scalar(found[1])
        if text:
            known.append({"field": field, "label": label, "value": text})
    return known


def _find_adjournment(context: dict) -> tuple[str, str] | None:
    """(where, entry text) for the first entry that mentions an adjournment."""
    for where, text in _all_texts(context):
        if "adjourn" in text.lower():
            return where, text
    return None


def _stage_guidance(context: dict) -> tuple[str, dict] | None:
    """(stage value, guidance answer for that stage) when a stage is stated."""
    found = _lookup(
        context,
        ("current_case_stage", "case_stage", "stage", "present_stage"),
    )
    if not found:
        return None
    stage = _scalar(found[1])
    if not stage:
        return None
    return stage, match_guidance(stage)


def _latest_order_text(context: dict) -> tuple[str, str] | None:
    """(where, text) of an order's own words, if the context carries any."""
    for key in ORDER_TEXT_KEYS:
        value = context.get(key)
        if isinstance(value, str) and value.strip():
            return key, value.strip()

    listing = _list_field(context, ORDER_LIST_KEYS)
    if listing:
        key, entries = listing
        for index in range(len(entries) - 1, -1, -1):
            entry = entries[index]
            if isinstance(entry, dict):
                for text_key in ("order_text", "order_details", "text",
                                 "content", "summary", "description"):
                    value = entry.get(text_key)
                    if isinstance(value, str) and value.strip():
                        return f"{key}[{index}].{text_key}", value.strip()
            elif isinstance(entry, str) and entry.strip():
                return f"{key}[{index}]", entry.strip()
    return None


def answer_case_question(
    question: str,
    case_context: dict | None = None,
) -> dict:
    """Answer one question, only from `case_context`.

    Returns the answer plus what it was drawn from (`source`), what
    was missing (`missing_information`) and whether it was grounded at
    all (`grounded`). A question the context cannot answer comes back
    as a plain statement that the information is not there.
    """
    text = " ".join((question or "").split())
    context = _clean_context(case_context)
    question_type = classify_question(text)

    known = _known_facts(context)
    warnings = [STANDING_WARNING]
    missing: list[str] = []
    next_steps: list[str] = []
    simplified_order: dict | None = None
    answer = ""
    grounded = False
    source: dict | None = None

    disclaimer = load_guidance_data()["disclaimer"]

    if question_type == "next_hearing_date":
        found = _lookup(context, (
            "next_hearing_date", "next_date", "nextDate",
            "next_date_of_hearing", "hearing_date", "next_hearing",
        ))
        value = _scalar(found[1]) if found else None
        if value:
            answer = (
                f"Based on the available case information, the next "
                f"hearing date is {value}."
            )
            grounded = True
            source = {"field": found[0], "value": value}
        else:
            answer = (
                f"{_NOT_STATED} next hearing date. Check your latest "
                f"notice or the court's cause list for the date."
            )
            missing.append("next_hearing_date")

    elif question_type == "adjournment_reason":
        adjournment = _find_adjournment(context)
        if adjournment is None:
            answer = (
                "The available case information does not mention any "
                "adjournment."
            )
            missing.append("adjournment entry")
        else:
            where, entry = adjournment
            quoted = entry.strip().rstrip(".!?")
            reason = _REASON_MARKERS.search(entry)
            if reason:
                answer = (
                    f"Based on the available case information, the matter "
                    f"was adjourned as recorded here: “{quoted}”."
                )
                grounded = True
                source = {"field": where, "value": entry}
            else:
                answer = (
                    f"{_NOT_STATED} reason for the adjournment. The entry "
                    f"on record is: “{quoted}”."
                )
                source = {"field": where, "value": entry}
                missing.append("reason for the adjournment")

    elif question_type == "current_stage":
        staged = _stage_guidance(context)
        if staged:
            stage, guidance = staged
            answer = (
                f"Based on the available case information, the matter is "
                f"at the stage: “{stage}”."
            )
            if guidance.matched:
                answer += (
                    f" In the guidance set that stage means: "
                    f"{guidance.response['why']}"
                )
                next_steps.append(
                    f"You may consider: "
                    f"{guidance.response['what_to_do_next']}"
                )
            grounded = True
            source = {"field": "case_stage", "value": stage}
        else:
            answer = f"{_NOT_STATED} current stage of the case."
            missing.append("case_stage")

    elif question_type == "case_status":
        found = _lookup(context, ("case_status", "status", "status_text"))
        value = _scalar(found[1]) if found else None
        if value:
            answer = (
                f"Based on the available case information, the case "
                f"status is: “{value}”."
            )
            grounded = True
            source = {"field": found[0], "value": value}
        else:
            answer = f"{_NOT_STATED} status of the case."
            missing.append("case_status")

    elif question_type == "order_explanation":
        order = _latest_order_text(context)
        if order is None:
            answer = (
                "The available case information does not include the "
                "text of any order, so it cannot be explained here."
            )
            missing.append("order text")
        else:
            where, order_text = order
            simplified = simplify_legal_text(order_text)
            simplified_order = {
                "source_field": where,
                "original_text": simplified.original_text,
                "simple_english": simplified.simple_english,
                "warnings": list(simplified.warnings),
            }
            answer = (
                "In plain English, the available order reads: "
                f"{simplified.simple_english}"
            )
            for warning in simplified.warnings:
                if warning not in warnings:
                    warnings.append(warning)
            grounded = True
            source = {"field": where, "value": simplified.simple_english}

    elif question_type == "what_to_do_next":
        staged = _stage_guidance(context)
        if staged:
            stage, guidance = staged
            if guidance.matched:
                answer = (
                    f"Based on the stage recorded in the available case "
                    f"information — “{stage}” — you may consider: "
                    f"{guidance.response['what_to_do_next']}"
                )
                next_steps.append(
                    f"You may consider: "
                    f"{guidance.response['what_to_do_next']}"
                )
                grounded = True
                source = {"field": "case_stage", "value": stage}
            else:
                answer = (
                    f"The available case information records the stage "
                    f"as “{stage}”, but that stage is not one the "
                    f"guidance set covers, so no stage-specific next "
                    f"step is offered."
                )
                missing.append("matching guidance for this stage")
        else:
            answer = (
                f"{_NOT_STATED} current stage of the case, so no "
                f"stage-specific next step can be given. If you say "
                f"which stage or notice your case is at, it can be "
                f"matched to the guidance set."
            )
            missing.append("case_stage")

    else:  # general — say what is known, and what is not
        if known:
            listing = "; ".join(
                f"{item['label']} {item['value']}" for item in known[:6]
            )
            answer = (
                f"Based on the available case information: {listing}."
            )
            source = {"field": "case_context", "value": listing}
            grounded = True
        else:
            answer = (
                "No case information was supplied with this question, "
                "so there is nothing to answer it from."
            )
            missing.append("case_context")

        # Point at the fields the question is about but the context
        # does not have, so a specific question says precisely what is
        # missing. Only questions that actually ask something get this;
        # "tell me about my case" is not a question about case type.
        if re.search(r"\b(why|what|when|where|who|which|how)\b", text, re.I):
            asked = set(re.findall(r"[a-z]{4,}", text.lower()))
            labels_present = {item["field"] for item in known}
            for field, label, _aliases in FIELD_LABELS:
                if field in labels_present:
                    continue
                if asked & set(label.split()):
                    missing.append(label)

        if not missing:
            answer += (
                " The supplied case information does not state anything "
                "about the specific point you asked."
            )
            warnings.append(UNCOVERED_WARNING)

    if not grounded:
        warnings.append(UNCOVERED_WARNING)

    seen: list[str] = []
    for warning in warnings:
        if warning not in seen:
            seen.append(warning)

    # The stage this answer was built around, as the case information
    # states it — None when it does not, never a stage guessed from
    # the question's wording.
    stage_found = _lookup(
        context,
        ("current_case_stage", "case_stage", "stage", "present_stage"),
    )
    current_stage = _scalar(stage_found[1]) if stage_found else None

    return {
        "mode": "case",
        "question": text,
        "question_type": question_type,
        "answer": answer,
        "grounded": grounded,
        "source": source,
        "current_stage": current_stage,
        "known_case_facts": known,
        "supporting_case_facts": known,
        "next_steps": next_steps,
        "simplified_order": simplified_order,
        "missing_information": missing,
        "warnings": seen,
        "answered_at": _now(),
        "disclaimer": disclaimer,
    }

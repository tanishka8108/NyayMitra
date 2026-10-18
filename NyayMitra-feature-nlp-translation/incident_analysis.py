"""
Incident analysis — the NLP half of "What Happened?", workflow 1.

A person describes, in their own words, what happened to them. This
module turns that into a structured, *hedged* reading:

    mode                   always "incident" — this is the incident
                           workflow, never the case workflow
    original_input         their message, exactly as sent
    what_user_described    everything they have said in this
                           conversation, back to them untouched
    possible_issue         what it may involve — never a conclusion
    simple_explanation     the same account in plain English
    facts                  only what is literally in the text (or was
                           established earlier in the conversation)
    missing_information    what would make the reading sharper
    next_steps             general, considered options
    evidence_to_preserve   worth keeping hold of
    urgency                the urgency adapter's answer — "not
                           available" until a model exists
    warnings               what this analysis cannot promise
    confidence             how much concrete detail it had to work with
    classification         where the category came from (Member 2's
                           model, or keyword matching — said out loud)

The pipeline is the one the feature specifies:

    user incident -> Member 2 classification (when connected) ->
    interpretation -> Member 1 incident knowledge -> possible issue ->
    simple explanation -> next steps -> evidence -> urgency -> (the
    endpoint adds translation)

Deliberately *not* in this pipeline: case-stage matching. An incident
is not a court stage, and a description of something that happened to
somebody must not be answered with "Notice issued to respondent".
Stage guidance belongs to the case workflow
(`case_companion.py`) and to /api/guidance, both of which keep using
the shared `guidance_matching` engine untouched.

Four rules the whole module is built to keep:

  1. Nothing is invented. No facts, no sections, no dates, no case
     status, no hearing dates, no reasons, no crime conclusions, no
     urgency band. A `fact` here is a substring of what the person
     actually wrote (or a value they supplied earlier), and "no
     category matched" is reported as such instead of filled in with
     a guess.

  2. The language stays conditional — "Based on what you described",
     "may involve", "not sufficient to determine", "You may consider".
     The one flat sentence is the low-confidence warning:
     "More information is needed to understand this situation
     accurately."

  3. It reuses, it does not re-implement. Plain-English rewriting comes
     from `legal_simplification`, category knowledge from
     `incident_knowledge` (a loader for Member 1's files that reports
     honestly when they are not there), classification from
     `incident_classification` (Member 2's adapter — None while the
     model is unconnected), and urgency from `urgency_adapter` (which
     answers "not available" until a model exists).

  4. Where an answer came from is part of the answer. The
     `classification` block names the source of the category, and the
     warnings say plainly when the model is not connected.
"""

from __future__ import annotations

import re

from incident_classification import classify, classifier_status
from incident_knowledge import find_category, knowledge_status, load_knowledge
from legal_simplification import MONTHS, simplify_legal_text
from next_steps_guidance_lookup import load_guidance_data
from urgency_adapter import assess_urgency

# The one unconditional sentence in the whole analysis. It is what the
# screen shows when there is not enough here to say anything useful.
LOW_CONFIDENCE_WARNING = (
    "More information is needed to understand this situation accurately."
)

STANDING_WARNING = (
    "This reading is based only on what you described. It does not "
    "establish any fact, case status, date, reason or legal conclusion."
)

KNOWLEDGE_UNAVAILABLE_WARNING = (
    "Category-specific incident knowledge is not loaded yet, so the "
    "next steps, evidence notes and questions below are the general "
    "ones rather than guidance for this kind of incident."
)

NO_CATEGORY_WARNING = (
    "This description could not be matched to a known incident "
    "category, so the next steps and questions below are the general "
    "ones."
)

# Appended while Member 2's model is unconnected, so nobody reads the
# category as a trained model's verdict. The text comes from
# `incident_classification` at call time — one source of truth for
# that sentence, and it flips the moment the model is registered.
CLASSIFICATION_HEDGE = (
    "The exact legal classification depends on the circumstances."
)

# Neutral, information-gathering prompts. These ask for details; they
# assert nothing. The `when` / `where` / `who` rows are only added when
# nothing in the description already answers them.
GENERIC_QUESTIONS: list[tuple[str, str]] = [
    ("when", "When did this happen? An approximate date or month is enough."),
    (
        "where",
        "Where did it happen — which place, area, police station or court?",
    ),
    ("who", "Who else was involved (names or roles)?"),
    (
        "documents",
        "Do you have any papers, messages, receipts or recordings about it?",
    ),
    (
        "development",
        "What happened most recently — the latest message, notice or event?",
    ),
]

# What the analysis says when no knowledge file covers this incident.
# Every line is an option, not an instruction, and none of them
# presumes a court stage.
GENERAL_NEXT_STEPS = [
    "You may consider writing down exactly what happened — when, "
    "where, and who was involved — while the details are still fresh.",
    "You may consider preserving any messages, recordings, receipts "
    "or documents connected with this.",
    "You may consider speaking with a qualified legal aid worker or "
    "advocate about your situation.",
    "If there is an immediate safety concern, seek appropriate "
    "emergency assistance.",
]

_CLOSING_STEP = (
    "Treat any deadline printed on your own papers as real, whatever "
    "this analysis says."
)

_GENERIC_EVIDENCE = [
    "You may consider keeping copies of any documents, receipts, "
    "messages or recordings connected with this.",
    "You may consider noting down the dates, places and people "
    "involved while they are still fresh.",
    "You may consider keeping the original of anything you plan to "
    "show to a lawyer, a legal aid worker or a court.",
]

URGENCY_INDICATOR_NOTE = (
    "These are general notes recorded for this incident category in "
    "the knowledge files — not an assessment of this situation."
)

# ---------------------------------------------------------------------------
# What is *in* the text. Every pattern below extracts a substring of the
# description; nothing is normalised, inferred or completed. This is the
# opposite of a named-entity model guessing at prose: a date only exists
# here if the person typed a date.
# ---------------------------------------------------------------------------

_DATE_DMY = re.compile(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{4}\b")
_DATE_ISO = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_MONTHS_RE = "|".join(MONTHS)
_DATE_ORDERED = re.compile(
    r"\b\d{1,2}(?:st|nd|rd|th)?\s+(?:" + _MONTHS_RE + r")\s+\d{4}\b",
    re.IGNORECASE,
)
_DATE_MONTH_FIRST = re.compile(
    r"\b(?:" + _MONTHS_RE + r")\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}\b",
    re.IGNORECASE,
)

_AMOUNT = re.compile(
    r"(?:₹|rs\.?\s*|inr\s*)[\d,]+(?:\.\d+)?"
    r"|\b[\d,]+(?:\.\d+)?\s*(?:rupees|lakh|lakhs|crore|crores)\b",
    re.IGNORECASE,
)

_CNR = re.compile(
    r"\bCNR\s*(?:(?:is|no\.?|number)\s*)?[:#]?\s*"
    r"([A-Za-z]{2,6}[A-Za-z0-9]{9,18})\b",
    re.I,
)
# A bare CNR is sixteen characters: four letters then twelve digits.
_CNR_BARE = re.compile(r"\b[A-Z]{4}\d{12}\b")
_LABELED_REFERENCE = re.compile(
    r"\b(?:case|civil|criminal|suit|petition|filing|transaction|txn|"
    r"reference|order|receipt|complaint|acknowledgement|passbook|file)"
    r"\s*(?:no\.?|number|#|id)?\s*(?:is\s+)?[:#]?\s*"
    r"([A-Za-z0-9][A-Za-z0-9/\-]{2,})",
    re.IGNORECASE,
)
_SECTION = re.compile(
    r"\bSection\s+\d+[A-Z]?(?:\s*\(\s*\d+\s*\))?"
    r"(?:\s+of\s+the\s+[A-Za-z][A-Za-z ]{3,60})?"
)
_COURT = re.compile(
    r"\b(?:[A-Z][a-zA-Z]+\s+){0,5}(?:High Court|District Court|"
    r"Sessions Court|Civil Court|Family Court|Consumer Court|"
    r"Labour Court|Tribunal|Magistrate Court|Court of the"
    r"(?:\s+[A-Z][a-zA-Z]+){0,3})\b"
)
_NAMED_PERSON = re.compile(
    r"\b(?:Mr|Mrs|Ms|Shri|Smt|Dr)\.?\s+"
    r"([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)"
)
_PHONE = re.compile(r"\b\d{10}\b")

_PLACE = re.compile(
    r"\b(?:in|at|near|outside|from|to)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)"
)

# "yesterday" is a when, even though it is not a date anybody could
# look up — it belongs in the signal, not in `facts`.
_RELATIVE_TIME = re.compile(
    r"\b(yesterday|today|tomorrow|last week|this week|next week|"
    r"last month|this month|next month|last year|last night|"
    r"earlier this (?:week|month|year)|this (?:week|month|year))\b",
    re.IGNORECASE,
)

_DOCUMENT_WORDS = re.compile(
    r"\b(documents?|receipts?|papers?|messages?|emails?|sms|letters?|"
    r"notices?|recordings?|photos?|videos?|agreements?|contracts?|"
    r"copies|proof|evidence)\b",
    re.IGNORECASE,
)


def _detected(description: str) -> list[dict]:
    """Facts literally present in the description, in order of appearance."""
    found: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def add(kind: str, value: str) -> None:
        value = value.strip()
        if not value:
            return
        key = (kind, value.lower())
        if key in seen:
            return
        # A detected fact has to be a substring of what was written —
        # this is the assertion that keeps extraction honest.
        if value.lower() not in description.lower():
            return
        # "case because ..." / "civil court" are the keyword patterns
        # running into the next word. A real case, filing or
        # transaction number carries a digit; prose does not.
        if kind == "reference" and not any(ch.isdigit() for ch in value):
            return
        seen.add(key)
        found.append({"type": kind, "value": value, "source": "detected"})

    patterns: list[tuple[str, re.Pattern]] = [
        ("date", _DATE_DMY),
        ("date", _DATE_ISO),
        ("date", _DATE_ORDERED),
        ("date", _DATE_MONTH_FIRST),
        ("amount", _AMOUNT),
        ("cnr", _CNR),
        ("cnr", _CNR_BARE),
        ("reference", _LABELED_REFERENCE),
        ("legal_section", _SECTION),
        ("court", _COURT),
        ("person", _NAMED_PERSON),
        ("phone", _PHONE),
    ]

    for kind, pattern in patterns:
        for match in pattern.finditer(description):
            # Named captures (CNR, person) are the interesting part;
            # otherwise take the whole match.
            add(kind, match.group(1) if match.groups() else match.group(0))

    return found


def _signals(description: str, facts: list[dict], known_facts: dict) -> dict:
    """What the description already answers, for the missing-information pass."""
    has_date = (
        any(f["type"] == "date" for f in facts)
        or bool(_DATE_DMY.search(description))
        or bool(_RELATIVE_TIME.search(description))
    )
    has_place = bool(_COURT.search(description)) or bool(_PLACE.search(description))
    has_person = any(f["type"] == "person" for f in facts) or any(
        str(key).lower() in {"person", "people", "party", "name", "involved"}
        for key in known_facts
    )
    has_documents = bool(_DOCUMENT_WORDS.search(description))
    return {
        "when": has_date,
        "where": has_place,
        "who": has_person,
        "documents": has_documents,
    }


def _missing_information(
    knowledge_questions: list[str],
    signals: dict,
    category_matched: bool,
) -> list[str]:
    questions = [q for q in knowledge_questions if q][:4]

    if not category_matched:
        # Without a category the analysis does not know which details
        # are essential, so it says so rather than staying silent.
        questions.append(
            "A sentence or two more about what exactly happened would "
            "help place this in the right category."
        )

    for key, prompt in GENERIC_QUESTIONS:
        if len(questions) >= 6:
            break
        if not signals.get(key):
            questions.append(prompt)

    return questions


def _confidence(
    words: int,
    signals: dict,
    category_matched: bool,
    knowledge_loaded: bool,
    model_confidence: float | None = None,
) -> dict:
    """How much there was to read — not what any of it means.

    When Member 2's model has classified this text, its own confidence
    is reported as-is, with the source said plainly in `basis`.
    Otherwise the score only says how much concrete detail the
    description carried. It never predicts an outcome.
    """
    if model_confidence is not None:
        score = round(min(max(model_confidence, 0.0), 1.0), 2)
        level = "high" if score >= 0.75 else "medium" if score >= 0.5 else "low"
        return {
            "level": level,
            "score": score,
            "basis": (
                "Confidence reported by the incident classification "
                "model for this description. It measures the model's "
                "own certainty, not the strength of any legal position."
            ),
        }

    score = 0.15  # something was said, so not zero
    if words >= 10:
        score += 0.10
    if words >= 30:
        score += 0.10
    if words >= 60:
        score += 0.05
    if signals["when"]:
        score += 0.15
    if signals["where"]:
        score += 0.10
    if signals["who"]:
        score += 0.10
    if signals["documents"]:
        score += 0.05
    if category_matched:
        score += 0.15
    if knowledge_loaded:
        score += 0.05

    score = round(min(score, 1.0), 2)
    level = "high" if score >= 0.75 else "medium" if score >= 0.5 else "low"

    basis = (
        f"{words} words of description; "
        f"{'when' if signals['when'] else 'no date'}, "
        f"{'where' if signals['where'] else 'no place'}, "
        f"{'who' if signals['who'] else 'no named person'}; "
        f"incident category "
        f"{'matched' if category_matched else 'not matched'}. "
        "It measures how much concrete detail is present, not how "
        "strong any legal position is."
    )
    return {"level": level, "score": score, "basis": basis}


def _resolve_category(knowledge, text: str, classification: dict | None):
    """Which incident category applies, and where the answer came from.

    Member 2's model wins when it is connected and names one; the
    model's id is then matched against Member 1's knowledge so the
    category's legal issue, next steps and questions still come from
    the dataset. With no model (or no category from it), keyword
    matching over Member 1's files decides — and deciding "none" is a
    valid answer, not a gap to fill.
    """
    model_category = (classification or {}).get("incident_category")
    if model_category:
        known = next(
            (
                entry
                for entry in knowledge.categories
                if entry["id"] == model_category
                or entry["label"].lower() == model_category.lower()
            ),
            None,
        )
        if known:
            return known, "member2_model"
        # Member 2 named a category Member 1's files do not carry:
        # show it, attributed, with no invented detail around it.
        return {
            "id": model_category,
            "label": model_category,
            "keywords": [],
            "description": "",
            "possible_legal_issue": "",
            "urgency_indicators": [],
            "warnings": [],
            "related_case_stages": [],
        }, "member2_model"

    category = find_category(knowledge, text)
    return category, ("keyword_matching" if category else "none")


def analyze_incident(
    description: str,
    *,
    known_facts: dict | None = None,
    prior_description: str = "",
    language: str = "en",
) -> dict:
    """Read a description of what happened — hedged, and without guesses.

    `prior_description` is everything the person said earlier in this
    conversation, so a short follow-up ("It happened yesterday") is
    read together with the account it refers to instead of on its own.

    Raises ValueError on an empty description; the endpoint turns that
    into a 400. Everything else is returned as structure, including
    the things this analysis could *not* determine.
    """
    raw_input = description or ""
    turn = " ".join(raw_input.split())
    if not turn:
        raise ValueError("Nothing to analyze.")

    prior = " ".join((prior_description or "").split())
    text = f"{prior} {turn}".strip() if prior else turn

    provided = {
        str(key): str(value)
        for key, value in (known_facts or {}).items()
        if value is not None and str(value).strip()
    }

    knowledge = load_knowledge()
    classification = classify(text, language=language)
    category, category_source = _resolve_category(knowledge, text, classification)
    category_matched = category is not None

    detected = _detected(text)
    facts = list(detected)
    # Member 2's extracted facts, kept apart from what the person
    # literally typed so nobody mistakes a model's words for a quote.
    if classification:
        for key, value in list(classification.get("facts", {}).items())[:20]:
            if value not in {f["value"] for f in facts}:
                facts.append(
                    {"type": str(key), "value": str(value),
                     "source": "member2_model"}
                )
    facts.extend(
        {"type": "provided", "label": str(key), "value": value,
         "source": "provided"}
        for key, value in provided.items()
        if value not in {f["value"] for f in facts}
    )
    signals = _signals(text, detected, provided)

    per_category = knowledge.for_category(category["id"] if category else None)

    # -- possible issue: dataset wording first, a hedged label second,
    #    and "cannot tell" as a first-class answer. Never a court stage.
    legal_issue = per_category["possible_legal_issue"]
    if legal_issue:
        possible_issue = legal_issue
        if possible_issue.rstrip()[-1] not in ".!?":
            possible_issue += "."
    elif category_matched:
        possible_issue = (
            f"Based on what you described, this may involve "
            f"“{category['label']}”."
        )
    else:
        possible_issue = (
            "Based on what you described, it is not sufficient to "
            "determine what this situation may involve. A little more "
            "detail would let it be read against the known incident "
            "categories."
        )
    if category_matched and CLASSIFICATION_HEDGE.lower() not in possible_issue.lower():
        possible_issue = f"{possible_issue} {CLASSIFICATION_HEDGE}"

    # -- plain-English layer: their own words, restated. No stage
    #    sentence — this workflow does not know or care about stages.
    restated = simplify_legal_text(text)
    summary = restated.simple_english.strip()
    if summary and summary[-1] not in ".!?":
        summary += "."
    simple_explanation = f"Based on what you described: {summary}"

    # -- next steps: Member 1's per-category steps first, the general
    #    considered options when there is no category to draw on.
    next_steps = list(per_category["next_steps"])
    if not next_steps:
        next_steps = list(GENERAL_NEXT_STEPS)
    next_steps.append(_CLOSING_STEP)

    evidence = per_category["evidence"] or list(_GENERIC_EVIDENCE)

    # -- urgency: the adapter's answer, never a band of our own making.
    urgency = assess_urgency(text, classification)
    if per_category["urgency_indicators"]:
        urgency = dict(urgency)
        urgency["knowledge_indicators"] = list(
            per_category["urgency_indicators"]
        )
        urgency["knowledge_indicator_note"] = URGENCY_INDICATOR_NOTE

    warnings = [STANDING_WARNING]
    if knowledge.source != "files":
        warnings.append(KNOWLEDGE_UNAVAILABLE_WARNING)
    if not category_matched:
        warnings.append(NO_CATEGORY_WARNING)
    classifier = classifier_status()
    if not classifier["connected"] and classifier["message"]:
        warnings.append(classifier["message"])
    for warning in per_category["warnings"]:
        if warning not in warnings:
            warnings.append(warning)
    for warning in restated.warnings:
        if warning not in warnings:
            warnings.append(warning)

    model_confidence = (classification or {}).get("confidence")
    confidence = _confidence(
        words=len(text.split()),
        signals=signals,
        category_matched=category_matched,
        knowledge_loaded=knowledge.source == "files",
        model_confidence=model_confidence,
    )
    if confidence["level"] == "low":
        warnings.insert(1, LOW_CONFIDENCE_WARNING)

    return {
        "mode": "incident",
        "original_input": raw_input,
        "what_user_described": text,
        "possible_issue": possible_issue,
        "simple_explanation": simple_explanation,
        "facts": facts,
        "missing_information": _missing_information(
            knowledge_questions=per_category["questions"],
            signals=signals,
            category_matched=category_matched,
        ),
        "next_steps": next_steps,
        "evidence_to_preserve": evidence,
        "urgency": urgency,
        "warnings": warnings,
        "confidence": confidence,
        "incident_category": (
            {"id": category["id"], "label": category["label"]}
            if category
            else None
        ),
        "classification": {
            "source": category_source,
            "member2_connected": classifier_status()["connected"],
            "confidence": model_confidence,
            "note": classifier_status()["message"],
        },
        "knowledge": knowledge_status(),
        "disclaimer": load_guidance_data()["disclaimer"],
    }

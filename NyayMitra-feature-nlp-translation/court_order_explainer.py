"""Plain-language reading of a court order.

Extracted from ``translate_service.py`` so that both explain paths —
pasted text and an uploaded PDF — read the document through exactly
the same rules. Nothing here loads a model: an order is written in
standing language, and restating that language plainly is fast,
deterministic, and honest about what it actually saw.

If the words in front of us are not wording an order uses, the answer
says so rather than summarising a document it did not understand.
"""

from __future__ import annotations

import re

from glossary_matcher import find_glossary_matches

EXPLAIN_DISCLAIMER = (
    "This is a plain-language reading of the words in the file. "
    "It is not legal advice, and the original order is what "
    "governs the case."
)

NOT_RECOGNISED = {
    "heading": "No standard order wording was recognised",
    "plain": (
        "This order does not use the usual phrasing, so "
        "nothing has been summarised for you. Read it with "
        "your advocate before acting on it."
    ),
}

# The standing wording of an order, and what it means to the person
# reading it. Ordered so the first point is usually the headline.
ORDER_RULES = [
    (
        r"\b(adjourn\w*|postpon\w*|defer\w*)\b",
        "The hearing has been postponed",
        "The court has put this hearing off. A postponement decides "
        "nothing — the case simply returns on the next date.",
    ),
    (
        r"\b(reserved|reserved for judgment)\b",
        "Judgment is reserved",
        "Both sides have finished arguing. The judge will pass orders "
        "later, so the decision is not out yet.",
    ),
    (
        r"\b(granted|allowed|admitted|accepted)\b",
        "An application was allowed",
        "What one side asked for has been accepted, subject to whatever "
        "conditions the order sets out.",
    ),
    (
        r"\b(rejected|refused|dismissed|denied)\b",
        "An application was refused",
        "What one side asked for has been turned down. The order will "
        "say whether it can be challenged, and by when.",
    ),
    (
        r"\b(notice|summons)\b",
        "Notice goes to the other side",
        "The other party has been asked to respond. They must file "
        "their reply before the matter can be heard.",
    ),
    (
        r"\b(stay(ed|ing|s)?)\b",
        "The proceedings are stayed",
        "The case is on hold for now. No further step is taken until "
        "the stay is lifted.",
    ),
    (
        r"\b(bail)\b",
        "The order deals with bail",
        "It sets whether someone may be released, and on what "
        "conditions.",
    ),
    (
        r"\b(costs?)\b",
        "Costs are mentioned",
        "The order says who pays the expenses of this application, or "
        "of the case so far.",
    ),
    (
        r"\b(directed to\b|\bshall\s+(?:file|appear|produce|submit))\b",
        "The court gave a direction",
        "A party has been told to do something — file paper, appear, "
        "or produce a document — by a date.",
    ),
    (
        r"\b(interim|temporary)\b",
        "This looks like an interim order",
        "It is a direction given while the case is still running, not "
        "the final outcome.",
    ),
    (
        r"\b(final (?:order|judgment|decision)|judgment is pronounced"
        r"|decree)\b",
        "This looks like the final order",
        "The court has recorded its decision on the matter.",
    ),
]

DATE_PATTERNS = [
    r"\b\d{1,2}(?:st|nd|rd|th)?\s+"
    r"(?:January|February|March|April|May|June|July|August|September"
    r"|October|November|December)\s+\d{4}\b",
    r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
]


def order_dates(text: str, limit: int = 6) -> list[str]:
    """Every date the order mentions, in first-seen order, capped."""
    found: list[str] = []

    for pattern in DATE_PATTERNS:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            value = match.group(0)
            if value not in found:
                found.append(value)

    return found[:limit]


def first_sentence(text: str, limit: int = 340) -> str:
    """The opening sentence, shortened so it can head a summary."""
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return ""

    boundary = re.search(r"(?<=[.!?])\s", compact)
    head = compact[: boundary.start()] if boundary else compact

    if len(head) > limit:
        head = head[: limit - 1].rstrip() + "…"

    return head


def matching_points(text: str) -> list[dict[str, str]]:
    """The standing wording this text uses, restated plainly."""
    lowered = text.lower()

    points = [
        {"heading": heading, "plain": plain}
        for pattern, heading, plain in ORDER_RULES
        if re.search(pattern, lowered)
    ]

    return points or [dict(NOT_RECOGNISED)]


def glossary_terms(text: str) -> list[dict[str, str]]:
    return [
        {"term": item["formal_term"], "plain": item["plain_explanation_en"]}
        for item in find_glossary_matches(text)
    ]


def explain_text(text: str, *, fallback_summary: str = "Court order") -> dict:
    """Summary, plain-language points, dates and glossary terms."""
    return {
        "summary": first_sentence(text) or fallback_summary,
        "points": matching_points(text),
        "key_dates": order_dates(text),
        "terms": glossary_terms(text),
        "disclaimer": EXPLAIN_DISCLAIMER,
    }

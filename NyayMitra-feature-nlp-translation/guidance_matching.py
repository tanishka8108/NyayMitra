"""
Case-stage scoring — the one place that decides which of the fifty
guidance rules a piece of free text is talking about.

This block used to live inside `translate_service.py`, where only
`POST /api/guidance` could use it. The "What Happened?" incident
analysis needs the very same match (a description of an incident has to
land on a case stage before the guidance set can say what that stage
calls for), and the rule was never going to be copied — two scorers
that disagree would mean two different answers to the same question.
So the scoring moved here, unchanged, and both endpoints import it.

Nothing in this module is a model or a network call: it is pure
Python over `next_steps_guidance_v2.json`.

Public names:

    guidance_terms(text)            the words a stage is scored on
    guidance_weight(term)           outcome > subject > everything else
    score_guidance_rule(tokens, rule)   -> (score, coverage, shared)
    rank_guidance(text, rules)      -> (rows, eligible)
    match_guidance(text)            -> GuidanceMatch (the whole answer)
    MATCH_COVERAGE                  the bar an eligible rule must clear
    NEAR_COVERAGE / NEAR_MIN_WEIGHT what counts as an honest near miss
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from next_steps_guidance_lookup import (
    find_related_glossary_terms,
    load_guidance_data,
)

# Carried no signal when scoring. The generic nouns are in nearly every
# stage, so a match on them would rate every rule equally. The last line
# is different: these are the ordinary English words the stage phrases
# happen to be built out of — "for want of time" shares "want" with a
# sentence about wanting to open a shop, and "next date for compliance"
# shares "date" with almost any account of a court hearing. They are
# dropped on both sides, so a stage is scored on what makes it that
# stage and nothing else.
GUIDANCE_STOPWORDS = frozenset(
    """
    the a an to of for in on at by with and or not is be are was were it its
    this that from as within till under before after up no any shall will
    due when if then so such other another each every both few more most
    case matter
    want time next date part
    """.split()
)

# The words that decide what a stage *means*. They are weighted above the
# nouns around them for two reasons: a person's account usually contains
# the outcome and little else, and a rule carrying one of these that the
# account does not contain is being contradicted — which is exactly how
# "bail application was rejected" stays on a rejected rule instead of
# landing on the identical-looking "bail application allowed".
GUIDANCE_OUTCOMES = frozenset(
    """
    allowed granted rejected refused dismissed declined admitted withdrawn
    reserved disposed quashed restored remanded transferred extended
    released unserved filed pending cancelled
    """.split()
)

# The subject the stage is about. Weighed between the outcomes and the
# connective tissue: someone saying "bail" is talking about a bail rule,
# and a rule that is about bail outranks one that merely mentions an
# application.
GUIDANCE_SUBJECTS = frozenset(
    """
    bail appeal notice custody summons statement vakalatnama rejoinder
    review revision execution anticipatory accused interim stay
    condonation counter affidavit remand jurisdiction registrar
    """.split()
)


def guidance_terms(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z]+", text.lower())
        if len(token) > 1 and token not in GUIDANCE_STOPWORDS
    }


def guidance_weight(term: str) -> int:
    if term in GUIDANCE_OUTCOMES:
        return 3
    if term in GUIDANCE_SUBJECTS:
        return 2
    return 1


# A third of the stage's weighted vocabulary is a knife-edge: a
# single shared word in a three-word stage lands exactly there,
# so one word in three stops counting and one word in two still
# does.
MATCH_COVERAGE = 0.35

# Worth mentioning as "closest stages" when nothing cleared the
# bar, but never close enough to act on — and only if the shared
# words include one that carries weight. "Want" from "for want of
# time" is a connective in somebody's sentence about opening a
# shop, not a sign they are describing an adjournment.
NEAR_COVERAGE = 0.15
NEAR_MIN_WEIGHT = 2


def score_guidance_rule(tokens: set[str], rule: dict) -> tuple[float, float, int]:
    """(score, coverage, shared_weight) for one rule.

    All three are always computed — the caller needs to tell
    the difference between "nothing here at all" and "some of
    this is here, just not enough to act on", and between
    sharing a word that means something and sharing a
    connective, because only the first of those is worth
    offering back as a near miss.
    """
    stage_terms = guidance_terms(rule["case_stage"])

    if not stage_terms:
        return 0.0, 0.0, 0

    total = sum(guidance_weight(term) for term in stage_terms)
    shared = sum(
        guidance_weight(term) for term in stage_terms if term in tokens
    )
    coverage = shared / total

    # Description wording adds a little, but only for words long enough
    # to be specific — "court" and "date" appear in half the set.
    other_terms = (
        guidance_terms(rule["description"])
        | guidance_terms(rule["suggested_action"])
    ) - stage_terms

    secondary = sum(
        0.35
        for term in other_terms
        if len(term) >= 6 and term in tokens
    )

    return shared + secondary + coverage * 1.5, coverage, shared


def rank_guidance(text: str, rules: list[dict]) -> tuple[list[tuple], list[tuple]]:
    """Score every rule against `text`.

    Returns `(rows, eligible)`, both sorted best-first as
    `(score, coverage, shared_weight, rule)` tuples.

    Matching is decided on coverage, never on score. Score
    mixes in shared and secondary words, so a rule sharing two
    weight-1 words can out-score one that clears the bar on a
    single subject — and taking the top of that list would let
    a near miss occupy the answer. `eligible` is therefore the
    only list a caller may act on; `rows` exists for near misses
    and for saying how close the best attempt was.
    """
    tokens = guidance_terms(text)

    rows = [(*score_guidance_rule(tokens, rule), rule) for rule in rules]

    eligible = [row for row in rows if row[1] >= MATCH_COVERAGE]
    eligible.sort(key=lambda row: (row[0], row[1]), reverse=True)

    rows.sort(key=lambda row: (row[0], row[1]), reverse=True)

    return rows, eligible


# ---------------------------------------------------------------------------
# The shaped answer. Both callers — /api/guidance and the incident
# analysis — return this same object, so "what should I do now" never
# reads differently depending on which screen asked. Only the response
# *shape* lives here; logging and validation belong to the endpoint.
# ---------------------------------------------------------------------------


@dataclass
class GuidanceMatch:
    """One answer from the guidance set, with the numbers behind it."""

    response: dict
    matched: bool
    score: float
    coverage: float
    guidance_id: str | None


def match_guidance(text: str) -> GuidanceMatch:
    """Match free text to the closest case stage, shaped for the API."""
    data = load_guidance_data()
    rows, eligible = rank_guidance(text, data["guidance_v2"])

    if not eligible:
        best = rows[0] if rows else (0.0, 0.0, 0, None)
        return GuidanceMatch(
            response={
                "matched": False,
                "stage": None,
                "urgency": None,
                "why": "",
                "what_to_do_next": (
                    "Nothing you described matches a stage this service "
                    "covers, so nothing specific has been guessed. Say a "
                    "little more — a notice, a hearing date, an order, a "
                    "bail or custody situation — and it will match one of "
                    "the fifty stages in the guidance set. Meanwhile, treat "
                    "any deadline printed on your papers as real and speak "
                    "to a qualified advocate."
                ),
                "related_terms": [],
                # Rules that shared a word of real weight but not enough
                # to act on. A rule sharing only connectives — or nothing
                # — drops out rather than being offered as "closest".
                "candidates": [
                    {"stage": rule["case_stage"], "urgency": rule["urgency"]}
                    for _score, coverage, shared, rule in rows[:6]
                    if rule is not None
                    and coverage >= NEAR_COVERAGE
                    and shared >= NEAR_MIN_WEIGHT
                ][:3],
                "disclaimer": data["disclaimer"],
            },
            matched=False,
            score=best[0],
            coverage=best[1],
            guidance_id=None,
        )

    best_score, best_coverage, _shared, best_rule = eligible[0]

    return GuidanceMatch(
        response={
            "matched": True,
            "stage": best_rule["case_stage"],
            "urgency": best_rule["urgency"],
            "why": best_rule["description"],
            "what_to_do_next": best_rule["suggested_action"],
            "related_terms": [
                {"term": term["formal_term"], "plain": term["plain_explanation_en"]}
                for term in find_related_glossary_terms(
                    f"{best_rule['case_stage']} {best_rule['description']}"
                )
            ],
            "candidates": [],
            "disclaimer": data["disclaimer"],
        },
        matched=True,
        score=best_score,
        coverage=best_coverage,
        guidance_id=best_rule["guidance_id"],
    )

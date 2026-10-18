"""
Guidance matching — "what should I do now", from whatever the person said.

The guidance set is keyed by the fifty case-stage phrases the court
system uses. Somebody describing their situation in their own words
will not type those phrases, so the rule is matched by scoring the
words they did use against each rule's own vocabulary — the stage
phrases carry the weight, description wording only breaks ties.

This module used to live inside translate_service.py. It is a plain
Python module now (no torch, no FastAPI, no models) so that both the
`/api/guidance` endpoint and the "What Happened?" orchestration can
call the *same* scorer, and so the scorer can be imported by tests on
a machine that has none of the checkpoints installed.
"""

import re

from glossary_matcher import find_glossary_matches
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


def guidance_terms(text: str):
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
GUIDANCE_MATCH_COVERAGE = 0.35

# Worth mentioning as "closest stages" when nothing cleared the
# bar, but never close enough to act on — and only if the shared
# words include one that carries weight. "Want" from "for want of
# time" is a connective in somebody's sentence about opening a
# shop, not a sign they are describing an adjournment.
GUIDANCE_NEAR_COVERAGE = 0.15
GUIDANCE_NEAR_MIN_WEIGHT = 2


def score_guidance_rule(tokens, rule):
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


def match_guidance(text: str) -> dict:
    """Match what someone described to the closest case stage, and say
    what that stage calls for.

    The response shape is the body of POST /api/guidance. It is kept
    here so the endpoint and the "What Happened?" orchestration share
    one implementation instead of drifting apart.
    """
    data = load_guidance_data()
    tokens = guidance_terms(text)

    rows = [
        (*score_guidance_rule(tokens, rule), rule)
        for rule in data["guidance_v2"]
    ]

    # Matching is decided on coverage, never on score. Score
    # mixes in shared and secondary words, so a rule sharing two
    # weight-1 words can out-score one that clears the bar on a
    # single subject — and taking the top of that list would let
    # a near miss occupy the answer.
    eligible = [row for row in rows if row[1] >= GUIDANCE_MATCH_COVERAGE]
    eligible.sort(key=lambda row: (row[0], row[1]), reverse=True)

    rows.sort(key=lambda row: (row[0], row[1]), reverse=True)

    if not eligible:
        return {
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
                if coverage >= GUIDANCE_NEAR_COVERAGE
                and shared >= GUIDANCE_NEAR_MIN_WEIGHT
            ][:3],
            "disclaimer": data["disclaimer"],
        }

    best_score, best_coverage, _shared, best_rule = eligible[0]

    return {
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
    }


def glossary_terms_for(text: str) -> list:
    """Glossary readings for any legal term appearing in `text`.

    Used to explain legal language in the plain words the glossary
    already carries (English, Hindi and Marathi are all stored on
    every entry).
    """
    out = []

    for item in find_glossary_matches(text):
        out.append(
            {
                "term": item.get("formal_term", ""),
                "plain": item.get("plain_explanation_en", ""),
                "plain_hi": item.get("plain_explanation_hi"),
                "plain_mr": item.get("plain_explanation_mr"),
            }
        )

    return out

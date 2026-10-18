"""
Loader for Member 1's incident knowledge files.

The "What Happened?" analysis is meant to read four knowledge files
that Member 1's legal dataset work will produce:

    incident_categories.json    what kinds of incident exist, and the
                                words that suggest one
    incident_next_steps.json    category -> suggested next steps
    incident_questions.json     category -> clarifying questions worth
                                asking the person
    incident_facts.json         category -> facts to record / evidence
                                worth preserving

None of them exist yet, and this service must keep working — and must
never invent them. So this module is a *schema and loader only*:

  * a missing, unreadable or malformed file yields an empty section
    plus a note in `knowledge_status()`, never an exception;
  * the analysis in `incident_analysis.py` says out loud when the
    knowledge base is unavailable, rather than quietly pretending the
    general guidance set is category-specific advice;
  * the schemas below are the contract Member 1's files must satisfy —
    extra keys are ignored, wrong-shaped entries are skipped.

No legal content is hardcoded here. `DEV_EXAMPLE_KNOWLEDGE` is a
clearly-marked placeholder used by the tests to prove the loader path
works end to end; it is only ever used when
`NYAYMITRA_INCIDENT_DEV_EXAMPLE=1` and no real file is present.

Schemas (all also accept a bare list instead of the named top key):

  incident_categories.json
      {"categories": [{"id": str, "label": str, "keywords": [str, ...],
                       "description": str?,
                       "possible_legal_issue": str?,          # hedged
                       "urgency_indicators": [str, ...]?,     # general
                       "warnings": [str, ...]?,
                       "related_case_stages": [str, ...]?}]}

  incident_next_steps.json
      {"next_steps": {"<category_id>": [str, ...]}}
      (or [{"category_id": str, "steps": [str, ...]}, ...])

  incident_questions.json
      {"questions": {"<category_id>": [str, ...]}}

  incident_facts.json
      {"evidence": {"<category_id>": [str, ...]}}
      ("facts" is accepted as a synonym for "evidence")

The per-category fields map straight onto the analysis response:

      label / keywords      -> the incident category shown
      possible_legal_issue  -> the "what this may involve" section
      next_steps            -> "what you can consider doing"
      questions             -> "information we still need"
      evidence              -> "information / evidence to keep"
      urgency_indicators    -> listed inside `urgency`, clearly marked
                               as general notes for the category —
                               never as an assessment of this case
      warnings              -> appended to the response warnings

No urgency *level* comes from these files: a list of indicators is
knowledge, not a model's verdict, and the `urgency.status` field only
ever says "available" when an actual model produced it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

KNOWLEDGE_FILES = {
    "categories": "incident_categories.json",
    "next_steps": "incident_next_steps.json",
    "questions": "incident_questions.json",
    "facts": "incident_facts.json",
}

# Overridable so tests (and a later data drop) can point the loader
# somewhere other than the service directory.
KNOWLEDGE_DIR_ENV = "NYAYMITRA_INCIDENT_KNOWLEDGE_DIR"

DEV_EXAMPLE_ENV = "NYAYMITRA_INCIDENT_DEV_EXAMPLE"

# ---------------------------------------------------------------------------
# Clearly-marked dev example. NOT legal data, NOT a real category: it
# exists so the loader/analysis path can be exercised before Member 1's
# files land, and it is only returned when the dev-example flag is on.
# ---------------------------------------------------------------------------
DEV_EXAMPLE_KNOWLEDGE = {
    "categories": [
        {
            "id": "dev_example_only",
            "label": "Dev example category (placeholder, not legal data)",
            "keywords": ["dev example"],
            "description": "Placeholder entry used by automated tests.",
            "possible_legal_issue": (
                "Dev example possible legal issue (placeholder, not "
                "legal data)."
            ),
            "urgency_indicators": ["Dev example urgency indicator."],
            "warnings": ["Dev example warning (placeholder, not legal data)."],
            "related_case_stages": [],
        }
    ],
    "next_steps": {
        "dev_example_only": [
            "Dev example next step — replace this when "
            "incident_next_steps.json is delivered."
        ]
    },
    "questions": {
        "dev_example_only": ["Dev example clarifying question."]
    },
    "facts": {
        "dev_example_only": ["Dev example evidence note."]
    },
}


def knowledge_dir() -> Path:
    override = os.environ.get(KNOWLEDGE_DIR_ENV, "").strip()
    if override:
        return Path(override)
    return Path(__file__).parent


def _read_json(filename: str) -> tuple[object | None, str | None]:
    """(data, note). data is None when the file cannot be used."""
    path = knowledge_dir() / filename
    if not path.exists():
        return None, f"{filename} not found"
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle), None
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"{filename} could not be read ({type(exc).__name__})"


def _as_named_map(data: object, *keys: str) -> dict:
    """Accept `{key: {...}}`, `{...}` itself, or a list of pairs.

    When several keys are given (`"evidence"`, `"facts"`), the first
    one present wins — the loader is deliberately forgiving about
    Member 1's naming. Anything else (a string, a number, a list of
    strings) is the wrong shape for this section, so it becomes an
    empty map rather than being guessed at.
    """
    if isinstance(data, dict):
        for key in keys:
            inner = data.get(key)
            if isinstance(inner, dict):
                return {str(k): v for k, v in inner.items()}
            if isinstance(inner, list):
                return _pairs_to_map(inner)
        inner = data
        if isinstance(inner, dict):
            return {str(k): v for k, v in inner.items()}
        return {}
    if isinstance(data, list):
        return _pairs_to_map(data)
    return {}


def _pairs_to_map(entries: list) -> dict:
    out: dict = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        category_id = entry.get("category_id") or entry.get("id")
        if not category_id:
            continue
        for list_key in ("steps", "questions", "evidence", "facts"):
            if isinstance(entry.get(list_key), list):
                out[str(category_id)] = _strings(entry[list_key])
                break
    return out


def _strings(values: list) -> list[str]:
    return [str(v).strip() for v in values if isinstance(v, str) and v.strip()]


def _clean_categories(data: object) -> list[dict]:
    if isinstance(data, dict):
        entries = data.get("categories", [])
    elif isinstance(data, list):
        entries = data
    else:
        return []

    clean: list[dict] = []
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue
        category_id = entry.get("id")
        label = entry.get("label")
        if not category_id or not label:
            continue  # an id-less or label-less category cannot be used
        keywords = entry.get("keywords")
        urgency_indicators = entry.get("urgency_indicators")
        warnings = entry.get("warnings")
        legal_issue = entry.get("possible_legal_issue") or entry.get(
            "possible_issue"
        )
        clean.append(
            {
                "id": str(category_id),
                "label": str(label),
                "keywords": _strings(keywords) if isinstance(keywords, list) else [],
                "description": str(entry.get("description") or "").strip(),
                "possible_legal_issue": (
                    legal_issue.strip()
                    if isinstance(legal_issue, str)
                    else ""
                ),
                "urgency_indicators": _strings(urgency_indicators)
                if isinstance(urgency_indicators, list)
                else [],
                "warnings": _strings(warnings)
                if isinstance(warnings, list)
                else [],
                "related_case_stages": _strings(
                    entry.get("related_case_stages")
                    if isinstance(entry.get("related_case_stages"), list)
                    else []
                ),
            }
        )
    return clean


class IncidentKnowledge:
    """The four sections, loaded together, plus what is missing."""

    def __init__(self, source: str) -> None:
        self.source = source  # "files" | "dev-example" | "none"
        self.categories: list[dict] = []
        self.next_steps: dict[str, list[str]] = {}
        self.questions: dict[str, list[str]] = {}
        self.evidence: dict[str, list[str]] = {}
        self.notes: list[str] = []

    @property
    def available(self) -> dict[str, bool]:
        """Which of the four sections this instance actually carries."""
        return {
            "categories": bool(self.categories),
            "next_steps": bool(self.next_steps),
            "questions": bool(self.questions),
            "facts": bool(self.evidence),
        }

    @property
    def any_available(self) -> bool:
        return any(self.available.values())

    def for_category(self, category_id: str | None) -> dict:
        """The per-category sections, with empty values when absent."""
        if not category_id:
            return {
                "next_steps": [],
                "questions": [],
                "evidence": [],
                "possible_legal_issue": "",
                "urgency_indicators": [],
                "warnings": [],
            }
        category = next(
            (c for c in self.categories if c["id"] == category_id),
            None,
        )
        return {
            "next_steps": list(self.next_steps.get(category_id, [])),
            "questions": list(self.questions.get(category_id, [])),
            "evidence": list(self.evidence.get(category_id, [])),
            "possible_legal_issue": (category or {}).get(
                "possible_legal_issue", ""
            )
            or "",
            "urgency_indicators": list(
                (category or {}).get("urgency_indicators") or []
            ),
            "warnings": list((category or {}).get("warnings") or []),
        }


def load_knowledge() -> IncidentKnowledge:
    """Load whatever exists. Never raises on a bad or missing file."""
    sections: dict[str, tuple[object | None, str | None]] = {
        name: _read_json(filename) for name, filename in KNOWLEDGE_FILES.items()
    }

    notes = [note for _data, note in sections.values() if note]

    categories = _clean_categories(sections["categories"][0])
    next_steps = _as_named_map(sections["next_steps"][0], "next_steps")
    questions = _as_named_map(sections["questions"][0], "questions")
    evidence = _as_named_map(sections["facts"][0], "evidence", "facts")

    source = "files" if (categories or next_steps or questions or evidence) else "none"

    if source == "none" and os.environ.get(DEV_EXAMPLE_ENV, "").strip() == "1":
        example = DEV_EXAMPLE_KNOWLEDGE
        categories = _clean_categories(example["categories"])
        next_steps = dict(example["next_steps"])
        questions = dict(example["questions"])
        evidence = dict(example["facts"])
        source = "dev-example"
        notes.append("using clearly-marked dev example knowledge")

    knowledge = IncidentKnowledge(source)
    knowledge.categories = categories
    # Only string lists survive; a file with a number in it loses that
    # row rather than leaking a non-string into the analysis output.
    knowledge.next_steps = {k: _strings(v) for k, v in next_steps.items() if isinstance(v, list)}
    knowledge.questions = {k: _strings(v) for k, v in questions.items() if isinstance(v, list)}
    knowledge.evidence = {k: _strings(v) for k, v in evidence.items() if isinstance(v, list)}
    knowledge.notes = notes
    return knowledge


def find_category(knowledge: IncidentKnowledge, text: str) -> dict | None:
    """The category whose keywords this description hits most.

    Scored on weighted keyword hits (longer keywords are more specific,
    so they count for more) against a length floor, so one incidental
    word does not turn a vague description into a confident category.
    Returns None when nothing reaches the floor — "no category" is a
    truthful answer; guessing one would not be.
    """
    if not knowledge.categories or not text:
        return None

    haystack = text.lower()
    best: tuple[int, dict] | None = None

    for category in knowledge.categories:
        score = 0
        for keyword in category["keywords"]:
            needle = keyword.lower().strip()
            if not needle:
                continue
            if needle in haystack:
                # Floor of 1 so a single long, specific keyword still
                # counts; short common words need two hits to matter.
                score += max(len(needle) // 3, 1)
        if score and (best is None or score > best[0]):
            best = (score, category)

    # Two weighted characters of evidence before a category is claimed.
    if best is None or best[0] < 2:
        return None
    return best[1]


def knowledge_status() -> dict:
    """What the loader can see right now — for the API response."""
    knowledge = load_knowledge()
    return {
        "source": knowledge.source,
        "files": dict(knowledge.available),
        "notes": list(knowledge.notes),
    }

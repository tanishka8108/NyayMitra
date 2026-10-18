"""
Shared data access for the "Tell Us What Happened" ML layer.

Canonical locations, searched in this order by resolve_data_file():

  1. resources/            - files this feature owns and commits
                             (resources/intent_examples.json),
  2. data/raw/             - local working copies of the team data files
                             (git-ignored: data/ is never committed),
  3. TellUsWhatHappened/data/ - the original handoff files shipped by the
                             incident-data owner, used as a read-only
                             fallback so nothing there is ever modified and
                             the module still works if a copy is missing.

All loaders are cached at process level (lru_cache) so the JSON files are read
once per process.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RESOURCES_DIR = REPO_ROOT / "resources"
DATA_RAW_DIR = REPO_ROOT / "data" / "raw"
HANDOFF_DATA_DIR = REPO_ROOT / "TellUsWhatHappened" / "data"
MODELS_DIR = REPO_ROOT / "models"

SEARCH_ORDER = (RESOURCES_DIR, DATA_RAW_DIR, HANDOFF_DATA_DIR)


def resolve_data_file(name: str) -> Path:
    """Search resources/, then data/raw/, then the original handoff file."""
    for directory in SEARCH_ORDER:
        candidate = directory / name
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        f"Data file '{name}' not found in any of: "
        + ", ".join(str(d) for d in SEARCH_ORDER)
    )


@lru_cache(maxsize=None)
def load_json(name: str):
    """Read a JSON data file once per process."""
    with resolve_data_file(name).open(encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=None)
def load_intent_examples() -> list:
    """Intent examples with the _meta header element filtered out."""
    rows = load_json("intent_examples.json")
    return [
        row
        for row in rows
        if isinstance(row, dict) and "example" in row and "category_id" in row
    ]


@lru_cache(maxsize=None)
def load_intent_test_examples() -> list:
    """Held-out intent evaluation rows (resources/intent_test_examples.json)."""
    rows = load_json("intent_test_examples.json")
    return [
        row
        for row in rows
        if isinstance(row, dict) and "example" in row and "category_id" in row
    ]


@lru_cache(maxsize=None)
def load_intent_ood_examples() -> list:
    """Out-of-scope rows (resources/intent_ood_examples.json) - greetings,
    gibberish, cooking, weather, sports, unrelated chat. These must be
    refused by the guard, never answered."""
    rows = load_json("intent_ood_examples.json")
    return [
        row
        for row in rows
        if isinstance(row, dict) and "text" in row and row.get("out_of_scope")
    ]


@lru_cache(maxsize=None)
def load_incident_examples() -> list:
    return list(load_json("incident_examples.json"))


@lru_cache(maxsize=None)
def load_categories() -> dict:
    """category_id -> {"category_id", "category_name", ...}"""
    rows = load_json("incident_categories.json")
    return {row["category_id"]: row for row in rows}


@lru_cache(maxsize=None)
def load_expected_facts() -> dict:
    """category_id -> ordered list of expected fact_or_entity names."""
    rows = load_json("incident_facts.json")
    by_category: dict = {}
    for row in rows:
        by_category.setdefault(row["category_id"], []).append(row["fact_or_entity"])
    return by_category


def expected_facts(category_id: str) -> list:
    """Expected fact names for one category ([] when the category is unknown)."""
    return list(load_expected_facts().get(category_id, []))

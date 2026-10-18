"""
Incident category classifier (25 categories, INC001..INC025).

Same embedding approach as src/intent_classifier.py, but the reference set is
the team-owned data/raw/incident_examples.json (125 examples, 5 per category)
and labels come from data/raw/incident_categories.json.

Nearest examples are scored with cosine similarity, then aggregated per
category (best score wins for the category) so the result is a ranking of
categories rather than of individual example sentences.

Only called when the intent classifier returned INCIDENT.

Note on the output field: the pipeline exposes the category as a snake_case
slug of the category_name (e.g. "online_financial_fraud_unauthorized_digital_
transaction"), which is the shape Member 1's spec asked for. Use
resolve_category() to map a slug - or an INC id - back to the full record.
"""

from __future__ import annotations

import re

import numpy as np

from incident_data import load_categories, load_incident_examples
from sentence_encoder import embed_cached, embed_texts
from text_validation import validate_user_input

TOP_K_DEFAULT = 3
EMBEDDING_CACHE_FILE = "incident_category_embeddings.npz"


def _load_examples():
    rows = load_incident_examples()
    if not rows:
        raise RuntimeError("data/raw/incident_examples.json contains no examples.")
    texts = [str(row["example"]) for row in rows]
    labels = [str(row["category_id"]) for row in rows]
    return texts, labels


_INCIDENT_TEXTS, _INCIDENT_LABELS = _load_examples()
_INCIDENT_VECTORS = embed_cached(_INCIDENT_TEXTS, EMBEDDING_CACHE_FILE)

_CATEGORIES = load_categories()


def category_slug(category_name: str) -> str:
    """'Online financial fraud / unauthorized digital transaction'
    -> 'online_financial_fraud_unauthorized_digital_transaction'"""
    slug = re.sub(r"[^a-z0-9]+", "_", str(category_name).lower())
    return slug.strip("_")


_SLUG_TO_ID = {
    category_slug(meta["category_name"]): cid for cid, meta in _CATEGORIES.items()
}


def resolve_category(slug_or_id: str) -> dict | None:
    """Map a category slug (pipeline output) or an INC id back to the full
    category record: {"category_id", "category_name", "slug", ...}. None if
    nothing matches. Provided for Member 3's downstream lookup."""
    if not isinstance(slug_or_id, str):
        return None
    key = slug_or_id.strip()
    cid = key.upper() if key.upper() in _CATEGORIES else _SLUG_TO_ID.get(key)
    if cid is None:
        return None
    meta = _CATEGORIES[cid]
    return {
        "category_id": meta["category_id"],
        "category_name": meta["category_name"],
        "slug": category_slug(meta["category_name"]),
    }


def classify_incident_category(text: str, top_k: int = TOP_K_DEFAULT) -> dict:
    """Classify one incident narrative into an incident category.

    Returns {
      "category_id": "INC001",
      "category_name": "Online financial fraud / unauthorized digital transaction",
      "confidence": float,                       # best cosine similarity
      "top_matches": [{"category_id", "category_name", "similarity"}, ...]
    }

    Raises ValueError for invalid input (not a string, or empty after the
    HTML is stripped).
    """
    cleaned = validate_user_input(text)

    query = embed_texts([cleaned])[0]
    similarities = _INCIDENT_VECTORS @ query  # cosine per example

    # Best example score per category.
    best_by_category: dict = {}
    for idx, score in enumerate(similarities):
        cid = _INCIDENT_LABELS[idx]
        score = float(score)
        if cid not in best_by_category or score > best_by_category[cid]:
            best_by_category[cid] = score

    ranked = sorted(best_by_category.items(), key=lambda item: -item[1])[: max(1, top_k)]
    top_matches = [
        {
            "category_id": cid,
            "category_name": _CATEGORIES[cid]["category_name"],
            "similarity": round(score, 3),
        }
        for cid, score in ranked
    ]

    best = top_matches[0]
    return {
        "category_id": best["category_id"],
        "category_name": best["category_name"],
        "confidence": round(max(0.0, min(1.0, best["similarity"])), 3),
        "top_matches": top_matches,
    }

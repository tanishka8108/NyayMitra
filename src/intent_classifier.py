"""
3-way intent classifier: INCIDENT | CASE_QUESTION | FOLLOW_UP.

Nearest-neighbour over sentence-transformer embeddings
(paraphrase-multilingual-MiniLM-L12-v2 - see sentence_encoder.MODEL_NAME;
the prototype notebook used the English-only all-MiniLM-L6-v2), the approach
prototyped in notebooks/03_situation_matching_prototype.ipynb:

  * every example in resources/intent_examples.json is embedded once at module
    load (cached to models/intent_embeddings.npz),
  * a new input is embedded and compared with cosine similarity
    (embeddings are L2-normalised, so a dot product IS the cosine),
  * the decision rule is the best match among the top-5 neighbours (a plain
    majority vote over the same window was tried first, but it loses short
    follow-ups whose second-nearest neighbours are incident narratives),
  * confidence = mean cosine similarity of the winning label's neighbours in
    that top-5 window, so nonsense input comes back with a low confidence
    instead of a wrong-but-confident one.

DATA CAVEAT: the CASE_QUESTION and FOLLOW_UP examples were generated
synthesetically on 2026-10-04 and are flagged in the file's _meta header as
"synthetic, pending team review" - they have not been reviewed by the team
member who owns the incident data.
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np

from incident_data import load_intent_examples
from sentence_encoder import embed_cached, embed_texts
from text_validation import validate_user_input

INCIDENT = "INCIDENT"
CASE_QUESTION = "CASE_QUESTION"
FOLLOW_UP = "FOLLOW_UP"
VALID_INTENTS = (INCIDENT, CASE_QUESTION, FOLLOW_UP)

TOP_K = 5
EMBEDDING_CACHE_FILE = "intent_embeddings.npz"


def _load_examples():
    rows = load_intent_examples()
    if not rows:
        raise RuntimeError("resources/intent_examples.json contains no examples.")

    texts, labels = [], []
    for row in rows:
        label = str(row["category_id"]).strip().upper()
        if label not in VALID_INTENTS:
            raise RuntimeError(
                f"Unknown intent '{row['category_id']}' in intent_examples.json "
                f"(expected one of {VALID_INTENTS})"
            )
        texts.append(str(row["example"]))
        labels.append(label)
    return texts, labels


# Precompute every example embedding at module load (per spec).
_INTENT_TEXTS, _INTENT_LABELS = _load_examples()
_INTENT_VECTORS = embed_cached(_INTENT_TEXTS, EMBEDDING_CACHE_FILE)


def _rank(cleaned: str):
    """Cosine similarity of the query against every training example, plus the
    indices of the top-5 neighbours, best first."""
    query = embed_texts([cleaned])[0]
    similarities = _INTENT_VECTORS @ query  # cosine per example
    top_indices = np.argsort(-similarities)[: min(TOP_K, len(similarities))]
    return similarities, top_indices


def _decision(similarities, top_indices) -> tuple:
    """(winner label, confidence) - shared by both public entry points."""
    votes = defaultdict(list)
    for idx in top_indices:
        votes[_INTENT_LABELS[idx]].append(float(similarities[idx]))

    # Best match among the top-5 neighbours decides the intent.
    winner = _INTENT_LABELS[top_indices[0]]
    # Confidence = how strongly the top-5 window agrees with that label.
    confidence = float(np.mean(votes[winner]))
    return winner, round(max(0.0, min(1.0, confidence)), 3)


def classify_intent(text: str) -> dict:
    """Classify one free-text input into an intent.

    Returns {"intent": "INCIDENT"|"CASE_QUESTION"|"FOLLOW_UP",
             "confidence": float (0-1)}

    Decision rule: best match (nearest example) inside the top-5 neighbours;
    confidence is the mean cosine similarity of that label's neighbours in the
    window, so it drops for input that resembles nothing in the data.

    Raises ValueError for invalid input (not a string, or empty after the
    HTML is stripped).
    """
    cleaned = validate_user_input(text)
    similarities, top_indices = _rank(cleaned)
    winner, confidence = _decision(similarities, top_indices)
    return {"intent": winner, "confidence": confidence}


def classify_intent_detailed(text: str) -> dict:
    """classify_intent() plus the raw top-1 / top-2 similarities and two
    margins - the numbers behind the guard in incident_pipeline.

    Returns {
      "intent":      "INCIDENT"|"CASE_QUESTION"|"FOLLOW_UP",
      "confidence":  mean similarity of the winning label in the top-5 window,
      "top1":        similarity of the nearest training example,
      "top2":        similarity of the second-nearest training example,
      "margin":      top1 - top2 (nearest EXAMPLE vs second-nearest example),
      "label_margin": best neighbour of the winning label minus best
                      neighbour of any OTHER label (WINNER vs RUNNER-UP).
    }

    Why two: `margin` treats two near-duplicate examples of the SAME class as
    a tie, so it is small even when the answer is obvious (an input whose two
    nearest neighbours are both CASE_QUESTION scores ~0.05 and would be
    refused despite confidence 0.8). `label_margin` only counts distance to
    the best competing class, which is what ambiguity actually means; it is
    the one used by MARGIN_THRESHOLD. `margin` is kept for calibration
    tables because it is what the top-1 minus top-2 reading of the data
    shows.

    Raises ValueError for invalid input (not a string, or empty after the
    HTML is stripped).
    """
    cleaned = validate_user_input(text)
    similarities, top_indices = _rank(cleaned)
    winner, confidence = _decision(similarities, top_indices)

    top1 = float(similarities[top_indices[0]])
    top2 = (
        float(similarities[top_indices[1]]) if len(top_indices) > 1 else 0.0
    )
    runner_up = max(
        (
            float(similarities[i])
            for i in range(len(similarities))
            if _INTENT_LABELS[i] != winner
        ),
        default=0.0,
    )
    return {
        "intent": winner,
        "confidence": confidence,
        "top1": round(max(0.0, min(1.0, top1)), 3),
        "top2": round(max(0.0, min(1.0, top2)), 3),
        "margin": round(max(0.0, top1 - top2), 3),
        "label_margin": round(max(0.0, top1 - runner_up), 3),
    }


def intent_examples() -> list:
    """(text, label) pairs - handy for tests/debugging."""
    return list(zip(_INTENT_TEXTS, _INTENT_LABELS))

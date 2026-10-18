"""
Sentence-encoder helper for the "Tell Us What Happened" ML layer.

Loads a sentence-transformers model lazily, once per process, and offers an
optional on-disk embedding cache so module import stays fast after the first
run.

The encoder is MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
(384-dim, 50 languages incl. Hindi and Marathi) - switched from the original
English-only "all-MiniLM-L6-v2" so Hindi / Marathi / Hinglish inputs are
embedded in the same space as the English training examples. First run
downloads the model (~500 MB from the HuggingFace hub).

Cached artifacts are written to models/ with an explicit prefix:
  * models/intent_embeddings.npz            (3-way intent classifier)
  * models/incident_category_embeddings.npz (incident category classifier)

The cache is keyed by a SHA-256 of the model name + the exact texts that were
encoded, so editing any JSON data file - or changing MODEL_NAME - invalidates
it automatically and the .npz files are regenerated on the next run.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from incident_data import MODELS_DIR

MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

_model = None


def get_model():
    """Lazy singleton SentenceTransformer."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(MODEL_NAME)
    return _model


def embed_texts(texts: list) -> np.ndarray:
    """Encode texts -> L2-normalised float32 matrix (row-per-text)."""
    vectors = get_model().encode(
        list(texts), normalize_embeddings=True, show_progress_bar=False
    )
    return np.asarray(vectors, dtype=np.float32)


def embed_cached(texts: list, cache_filename: str) -> np.ndarray:
    """Encode texts, reusing models/<cache_filename> when it is still valid.

    Cache entries carry the SHA-256 of (model name + texts); a mismatch simply
    recomputes and overwrites the file. Caching failures are non-fatal - the
    embeddings are still returned from memory.
    """
    texts = [str(t) for t in texts]
    cache_key = hashlib.sha256(
        (MODEL_NAME + "\n" + "\n".join(texts)).encode("utf-8")
    ).hexdigest()

    cache_path = MODELS_DIR / cache_filename
    if cache_path.exists():
        try:
            with np.load(cache_path, allow_pickle=False) as cached:
                if (
                    str(cached["cache_key"]) == cache_key
                    and cached["vectors"].shape[0] == len(texts)
                ):
                    return np.asarray(cached["vectors"], dtype=np.float32)
        except Exception:
            pass  # stale/corrupt cache -> recompute

    vectors = embed_texts(texts)

    try:
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(cache_path, vectors=vectors, cache_key=cache_key)
    except Exception as exc:  # cache is an optimisation, never a hard failure
        print(f"Could not write embedding cache {cache_path}: {exc}")

    return vectors

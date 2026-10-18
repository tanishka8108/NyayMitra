"""
Shared input validation for the "Tell Us What Happened" ML layer.

There is no src/situation_matcher.py in this repo to reuse (only the notebook
prototype notebooks/03_situation_matching_prototype.ipynb), so this module is
the single place where free-text validation lives. Every entry point of this
feature (intent classification, incident-category classification, fact
extraction and the unified pipeline) calls validate_user_input() before doing
any work, so all of them behave identically on bad input.
"""

from __future__ import annotations

import bleach

# Free-text cap. Anything longer is truncated, never rejected silently.
MAX_INPUT_LENGTH = 1000

# Strip every HTML tag (and therefore all attributes); keep the inner text.
ALLOWED_TAGS: list = []
ALLOWED_ATTRIBUTES: dict = {}


def validate_user_input(text: object) -> str:
    """Clean and sanity-check one piece of user free text.

    Rules (in order):
      1. must be a string,
      2. HTML tags are stripped with bleach (``<b>hello</b>`` -> ``hello``),
      3. empty / whitespace-only / tag-only input is rejected with ValueError,
      4. length is capped at MAX_INPUT_LENGTH characters.

    Returns the cleaned text; raises ValueError when there is nothing usable.
    """
    if not isinstance(text, str):
        raise ValueError("Input must be a string.")

    cleaned = bleach.clean(
        text, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES, strip=True
    )
    cleaned = cleaned.strip()

    if not cleaned:
        raise ValueError("Input text is empty.")

    if len(cleaned) > MAX_INPUT_LENGTH:
        cleaned = cleaned[:MAX_INPUT_LENGTH]

    return cleaned

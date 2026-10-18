"""CNR validation helpers.

A CNR (Case Number Regular) is the 16 character identifier eCourts
allots to every case: four letters identifying the state and court
complex, then a twelve digit serial that ends in the filing year.
``MHPU210000042026`` is a Maharashtra / Pune CNR from 2026.

The format check exists so that a malformed identifier is rejected
with a 400 before any lookup happens — a bad CNR is a client error,
not a missing case — and so that whatever a caller sends can never be
passed through to a query or a log line unexamined.
"""

from __future__ import annotations

import re

# Four letters, then twelve digits. Letters and digits are never mixed
# after the four character court code.
CNR_PATTERN = re.compile(r"^[A-Z]{4}[0-9]{12}$")

CNR_LENGTH = 16

INVALID_CNR_MESSAGE = (
    "Invalid CNR format. A CNR is 16 characters: four letters followed "
    "by twelve digits, for example MHPU210000042026."
)


def normalize_cnr(raw: str) -> str:
    """Uppercase and strip the separators people paste in with a CNR."""
    if raw is None:
        return ""

    cleaned = str(raw).strip().upper()

    for separator in (" ", "-", "_", "\t", "\n"):
        cleaned = cleaned.replace(separator, "")

    return cleaned


def is_valid_cnr(raw: str) -> bool:
    """True when ``raw`` normalises to a well formed CNR."""
    return bool(CNR_PATTERN.match(normalize_cnr(raw)))


def validate_cnr(raw: str) -> str:
    """Return the normalised CNR, or raise ``ValueError`` with a message
    that is safe to show a caller."""
    cleaned = normalize_cnr(raw)

    if not cleaned:
        raise ValueError("A CNR is required.")

    if len(cleaned) != CNR_LENGTH or not CNR_PATTERN.match(cleaned):
        raise ValueError(INVALID_CNR_MESSAGE)

    return cleaned

"""Legal wording → simple English: the middle layer of three.

Every court order is offered to the reader in three steps::

    ORIGINAL LEGAL TEXT     what the court actually wrote
            ↓
    SIMPLE ENGLISH          the same words, in everyday language
            ↓
    MARATHI / HINDI         that plain English, translated

This module is step two. Step three translates *this* layer rather
than the legalese, which is why the Marathi answer reads the way a
person would say it instead of the way a statute is written.

What it does, and deliberately does not, do:

* It rewrites only wording that has an everyday equivalent — "the
  matter is adjourned" becomes "the hearing has been postponed" —
  using a fixed table, so the same input always gives the same
  output and no model is involved.
* Names, dates, case numbers, section numbers and citations are
  never touched: they pass through byte for byte.
* Nothing is added. A sentence with no plain equivalent comes back
  unchanged, because guessing at a court's words is exactly the
  failure this feature exists to avoid.

The rules are shared by both explain paths (uploaded PDF and pasted
text) so the three layers always line up however the order arrived.
"""

from __future__ import annotations

import re

# (pattern, replacement). Ordered longest-pattern-first at import so a
# phrase is matched before one of its own words ("costs are reserved"
# before "is reserved"). Case-insensitive; group references work.
SIMPLIFY_RULES: tuple[tuple[str, str], ...] = (
    # --- the standing wording of an order -----------------------------
    (r"\b(?:the )?matter is (?:hereby )?adjourned\b",
     "the hearing has been postponed"),
    (r"\b(?:the )?case is (?:hereby )?adjourned\b",
     "the hearing has been postponed"),
    (r"\badjournment\b", "postponement"),
    (r"\badjourned\b", "postponed"),
    (r"\badjourning\b", "postponing"),
    (r"\badjourn\b", "postpone"),
    (r"\bcosts are reserved\b",
     "the question of costs is kept for later"),
    (r"\bjudgment is reserved\b", "the decision will be given later"),
    (r"\breserved for judgment\b", "kept back for the decision"),
    (r"\bis reserved\b", "will be announced later"),

    # --- words only a draughtsman would choose ------------------------
    (r"\bhereinafter referred to as\b", ""),
    (r"\bhereinafter\b", ""),
    (r"\bhereby\b", ""),
    (r"\b(?:this|the) (?:Hon'ble|Honourable|Honorable) "
     r"(?:Court|court)\b", "the court"),
    (r"\b(?:Hon'ble|Honourable|Honorable)\b", ""),

    # --- the people in the room ---------------------------------------
    # The article is consumed with the phrase, so "the learned counsel"
    # becomes "the lawyer" rather than "the the lawyer".
    (r"\b(?:the )?learned counsel for\b", "the lawyer for"),
    (r"\b(?:the )?learned counsel\b", "the lawyer"),
    (r"\b(?:the )?learned advocates\b", "the lawyers"),
    (r"\b(?:the )?learned advocate\b", "the lawyer"),
    (r"\bthe opposite party\b", "the other side"),
    (r"\bopposite party\b", "other side"),

    # --- procedure, said plainly --------------------------------------
    (r"\bpursuant to\b", "under"),
    (r"\bperused\b", "read"),
    (r"\ban ex parte\b", "a one-sided"),
    (r"\bex parte\b", "one-sided"),
    (r"\bwithout prejudice to\b", "without affecting"),
    (r"\bwithout prejudice\b", "without hurting either side's case"),
    (r"\banticipatory bail\b", "bail before arrest"),
    (r"\bcharge[- ]sheet\b", "police report"),
    (r"\bfinal hearing\b", "main hearing"),
    (r"\bthe next date of hearing\b", "the next hearing date"),
    (r"\bissued notice\b", "sent notice"),
    (r"\btaken on file\b", "filed"),
    (r"\bprefer an appeal\b", "file an appeal"),
    (r"\binterim\b", "temporary"),
    (r"\bput up\b", "scheduled"),
    (r"\bnem con\b", "with nobody objecting"),
    (r"\bprayer\b", "request"),
    (r"\band/or\b", "or"),

    # --- referring back to something already named ---------------------
    (r"\b(?:the )?said (order|application|petition|matter)\b", r"this \1"),
    (r"\bthe above (order|application|petition|matter)\b", r"this \1"),
    (r"\b(?:the )?aforesaid\b", "that"),

    # --- abbreviations --------------------------------------------------
    (r"\bviz\.\b", "that is"),
    (r"\bi\.e\.\b", "that is"),
    (r"\be\.g\.\b", "for example"),
)

_COMPILED_RULES: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern, re.IGNORECASE), replacement)
    for pattern, replacement in sorted(
        SIMPLIFY_RULES, key=lambda rule: len(rule[0]), reverse=True
    )
)

_SENTENCE_START = re.compile(r"(^|[.!?][\"')\]]?\s|\n\s*)\Z")


def _starts_sentence(before: str) -> bool:
    """Did the match begin a sentence? If so its replacement may need a
    capital letter, the way the wording it replaced had one."""
    return bool(_SENTENCE_START.search(before))


def _apply(text: str, pattern: re.Pattern[str], replacement: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        value = match.expand(replacement)

        if (
            value
            and value[0].isalpha()
            and not value[0].isupper()
            and _starts_sentence(text[: match.start()])
        ):
            value = value[0].upper() + value[1:]

        return value

    return pattern.sub(_replace, text)


def _tidy(text: str) -> str:
    """Whitespace the rewrites can leave behind — never wording."""
    lines: list[str] = []

    for line in text.split("\n"):
        line = re.sub(r"[ \t]{2,}", " ", line)
        line = re.sub(r"\s+([,.;:])", r"\1", line)
        line = re.sub(r"([(\[])\s+", r"\1", line)
        line = re.sub(r"\s+([)\]])", r"\1", line)
        lines.append(line.strip())

    # Keep paragraph breaks, drop runs of them.
    out: list[str] = []
    previous_blank = False

    for line in lines:
        if not line:
            if previous_blank:
                continue
            previous_blank = True
            out.append("")
        else:
            previous_blank = False
            out.append(line)

    return "\n".join(out).strip()


def simplify_text(text: str | None) -> str:
    """The same words, in everyday language.

    Returns the input untouched when nothing in it had a plain
    equivalent, and the input as-is when a rewrite would have emptied
    it — a layer is never blanked out over wording.
    """
    if not text or not text.strip():
        return ""

    original = text
    result = text

    for pattern, replacement in _COMPILED_RULES:
        if not pattern.search(result):
            continue
        result = _apply(result, pattern, replacement)

    result = _tidy(result)

    if not result:
        return original.strip()

    if original[:1].isupper() and result[0].isalpha() and not result[0].isupper():
        result = result[0].upper() + result[1:]

    return result


def plain_summary(points: list[dict[str, str]] | None, limit: int = 2) -> str:
    """The rules' own reading of the document, in one or two sentences.

    Used as the document-level simple layer: "The hearing has been
    postponed. The court has put this hearing off…" is what the order
    *means*, which a one-line rewrite of an opening sentence cannot be.
    """
    sentences: list[str] = []

    for point in points or []:
        heading = (point.get("heading") or "").strip()
        plain = (point.get("plain") or "").strip()

        if not heading or not plain:
            continue

        sentence = f"{heading}. {plain}"

        if sentence not in sentences:
            sentences.append(sentence)

        if len(sentences) >= limit:
            break

    return " ".join(sentences)


def build_layers(
    legal: str | None,
    *,
    plain: str | None = None,
) -> dict[str, str | None]:
    """The three layers for one piece of text, untranslated.

    ``plain`` lets the caller supply the simple layer (the document
    level uses the reading above); otherwise it is the legal text
    rewritten in place.
    """
    if not legal or not legal.strip():
        return {"legal": None, "simple": None, "translated": None}

    simple = (plain or "").strip() or simplify_text(legal)

    return {"legal": legal, "simple": simple, "translated": None}

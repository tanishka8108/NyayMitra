"""Legal English -> plain English: the middle layer of NyayMitra.

    ORIGINAL LEGAL TEXT
           |
           v   (entity protection: dates, case numbers, CNR numbers,
                section numbers, amounts, names)
           v
    LEGAL SIMPLIFICATION ENGINE      <- this module
           |
           v
    SIMPLE ENGLISH
           |
           v   (glossary terms reported, then IndicTrans2)
    MARATHI / HINDI

Nothing in this module loads a model. Simplification is a rewrite of
one register of English into another, and it is done with rules that
can be read, audited and corrected -- which is the only honest way to
promise that no legal fact has been invented.

Three guarantees, in order of importance:

1. **Entities never move.** Dates, case numbers, CNR numbers, section
   numbers, monetary amounts and party/advocate/judge names are lifted
   out of the text before any rule runs and put back afterwards, so a
   rule can only ever rewrite the words *around* them.
2. **Ambiguity is never resolved.** If a sentence can be read two ways
   the system says so and leaves both readings standing; it never picks
   one.
3. **Low confidence falls back to the original.** A sentence that still
   carries archaic legal wording after the rules have run is not
   simplified -- the original is kept and a warning is attached, so the
   reader is told to look at the real text instead of trusting ours.

The rules live in ``legal_simplification_rules.json`` so that adding a
piece of standing wording is a data change, not a code change.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

RULES_PATH = Path(__file__).with_name("legal_simplification_rules.json")

# Long enough for a court order section, short enough that one request
# cannot turn into hundreds of translation chunks.
MAX_INPUT_CHARS = 20_000

LOW_CONFIDENCE_WARNING = (
    "Some legal wording could not be safely simplified. Please refer to "
    "the original text."
)

AMBIGUITY_WARNING = (
    "This wording can be read in more than one way, so nothing has been "
    "chosen for you here. Compare it with the original text."
)

UNPRESERVED_WARNING = (
    "These references could not be confirmed in the translated text: "
    "{items}. Please check the original text."
)

LEGAL_AID_DISCLAIMER = (
    "This is an aid to reading the words in a legal document. It is not "
    "legal advice, it decides nothing about your case, and the original "
    "document is what governs."
)

SUPPORTED_TARGET_LANGS = ("mar_Deva", "hin_Deva", "eng_Latn")

# ---------------------------------------------------------------------------
# Dates
#
# A date is only ever reformatted, never moved. `15.10.2026` becomes
# `15 October 2026` because that is what the reader of a plain-English
# layer needs -- but only when the reading is forced (day > 12, so it
# cannot be a month) or when day and month are the same number, so both
# readings agree. `10.11.2026` is left exactly as written: guessing
# which half is the day would be inventing a fact about a deadline.
# ---------------------------------------------------------------------------

MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)
_MONTH_RE = "|".join(MONTHS)

# The trailing guard refuses *more* date material (a second `2026.10`
# would mean this is not the whole date) but allows the full stop that
# ends the sentence -- `on 15.10.2026.` is a date, and a guard built
# from `[./-]` would have refused it and left the reader with dots.
_DMY_RE = re.compile(
    r"(?<![\d./-])(\d{1,2})[./-](\d{1,2})[./-](\d{4})(?!\d)(?!\.\d)(?![/-]\d)"
)
_YMD_RE = re.compile(
    r"(?<![\d./-])((?:19|20)\d{2})[./-](\d{1,2})[./-](\d{1,2})(?!\d)(?!\.\d)"
)
_ORDINAL_RE = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)\s+(" + _MONTH_RE + r")\s+(\d{4})\b",
    re.IGNORECASE,
)
_MONTH_FIRST_RE = re.compile(
    r"\b(" + _MONTH_RE + r")\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b",
    re.IGNORECASE,
)

_MONTH_INDEX = {name.lower(): index for index, name in enumerate(MONTHS, start=1)}


def _month_name(value: str) -> str:
    return MONTHS[_MONTH_INDEX[value.lower()] - 1]


def normalize_dates(text: str) -> str:
    """Re-read dates in the plainest form that is still the same date.

    Every rewrite keeps the day, month and year identical. Anything
    whose day/month order is genuinely unknown is returned untouched.
    """

    def _dmy(match: re.Match) -> str:
        day, month, year = int(match.group(1)), int(match.group(2)), match.group(3)
        if not (1 <= day <= 31 and 1 <= month <= 12):
            return match.group(0)
        # Day > 12 cannot be a month, so the order is forced.
        # day == month means both readings give the same date.
        if day <= 12 and day != month:
            return match.group(0)
        return f"{day} {_month_name(MONTHS[month - 1])} {year}"

    def _ymd(match: re.Match) -> str:
        year, month, day = match.group(1), int(match.group(2)), int(match.group(3))
        if not (1 <= day <= 31 and 1 <= month <= 12):
            return match.group(0)
        return f"{day} {_month_name(MONTHS[month - 1])} {year}"

    def _ordinal(match: re.Match) -> str:
        return f"{int(match.group(1))} {_month_name(match.group(2))} {match.group(3)}"

    def _month_first(match: re.Match) -> str:
        return f"{int(match.group(2))} {_month_name(match.group(1))} {match.group(3)}"

    text = _ORDINAL_RE.sub(_ordinal, text)
    text = _MONTH_FIRST_RE.sub(_month_first, text)
    text = _YMD_RE.sub(_ymd, text)
    return _DMY_RE.sub(_dmy, text)


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------

_CNR_RE = re.compile(
    r"\b(?:CNR\s*[:#.\-]?\s*[A-Za-z0-9]{4,25}|[A-Z]{4,}[0-9]{8,})\b"
)

# A case number carries its type with it -- `W.P. 1234/2026` and
# `Crl.M.A. 456/2024` are two *different* filings, so the prefix is
# taken whole rather than leaving `W.P.` for the model to transliterate
# into something no registry would recognise. The prefixed forms insist
# on an abbreviation and a slash-number, so `dated 15.10.2026` and
# `filed on 15/10/2026` cannot be swallowed as if they were filings.
_CASE_NO_RE = re.compile(
    r"\b(?:[A-Z]{1,5}\.?(?:\([A-Za-z]+\))?\.?\s+)+\d+(?:/\d+){1,3}\b"
    r"|\b(?:[A-Za-z]{1,6}\.){1,4}\s*\d+(?:/\d+){1,3}\b"
    r"|\b[A-Za-z][A-Za-z0-9.]*(?:/\d{1,6}){1,3}\b"
    r"|\b\d+(?:/\d+){1,3}\b"
    r"|\b\d{1,6}\s+(?:of|OF)\s+(?:19|20)\d{2}\b"
)
_AMOUNT_RE = re.compile(
    r"(?:Rs\.?|INR|₹|Rupees)\s*\.?\s*\d[\d,]*(?:\.\d+)?(?:\s*/-)?"
    r"|\b\d{1,3}(?:,\d{2,3})+(?:\.\d+)?\b"
)
_SECTION_RE = re.compile(
    r"\b(?:Sections?|Secs?\.?|Rules?|Clauses?|Articles?|Orders?)"
    r"\s+(?:\d+[A-Z]?(?:\([A-Za-z0-9]+\))*|[IVXLC]{1,7})(?![A-Za-z0-9])",
    re.IGNORECASE,
)
_DATE_RE = re.compile(
    r"\b\d{1,2}\s+(?:" + _MONTH_RE + r")\s+\d{4}\b"
    r"|\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b"
    r"|\b(?:19|20)\d{2}[./-]\d{1,2}[./-]\d{1,2}\b"
    r"|\b(?:" + _MONTH_RE + r")\s+\d{1,2},?\s+\d{4}\b",
    re.IGNORECASE,
)

# A title followed by a run of Capitalised tokens. `A.` is a token of its
# own so that `Justice A. Sharma` is taken whole instead of stopping at
# the initial. Newlines are not separators: a name does not wrap inside
# four tokens, and joining across a paragraph break would swallow the
# start of the next one.
_NAME_TOKEN = r"(?:[A-Z]\.|[A-Z][A-Za-z'’\-]*(?:\.(?=[ \t]+[A-Z]))?)"
_NAME_RUN = _NAME_TOKEN + r"(?:[ \t]*" + _NAME_TOKEN + r"){0,3}"
_TITLE_NAME_RE = re.compile(
    r"(?<![A-Za-z])"
    r"(?P<title>Mr|Mrs|Ms|Miss|Dr|Shri|Smt|Sri|Kumari|Kum|Sjt|Justice|Hon'ble|Hon"
    r"|Adv|Advocate|S/o|D/o|W/o|C/o)\.?"
    r"[ \t]+(?P<name>" + _NAME_RUN + r")"
)

# The court itself. A court name is a fact of the document: it says
# *which* court decided, so it travels in the script it was written in
# rather than being rendered afresh.
_COURT_RE = re.compile(
    r"\b(?:Supreme Court of India"
    r"|High Court of Judicature at [A-Za-z]+"
    r"|High Court"
    r"|District and Sessions Court|District Court|Sessions Court"
    r"|Family Court|Labour Court|Revenue Tribunal"
    r"|National Company Law Tribunal|National Green Tribunal"
    r"|Consumer Disputes Redressal Commission|Consumer Court"
    r"|Lok Adalat|Civil Court|Criminal Court"
    r"|Court of the Chief Judicial Magistrate"
    r"|Court of the Senior Civil Judge"
    r"|Court of the Civil Judge)\b",
    re.IGNORECASE,
)

# A named party, announced by the role the order gives it. The role
# word is matched case-insensitively on its own, so the name after it
# is still required to be written as one: `the petitioner is directed`
# has no name to take, and must not lose its verb.
_PARTY_NAME_RE = re.compile(
    r"\b(?i:petitioner|respondent|applicant|appellant|accused|complainant"
    r"|defendant|objector|intervenor)"
    r"(?:[ \t]+name)?[ \t]*,?[ \t]+(?P<name>" + _NAME_RUN + r")"
)

# A run of two or more ALL-CAPS tokens: party names and the court header.
_CAPS_RUN_RE = re.compile(r"\b[A-Z][A-Z'&.\-]*(?:[ ,]+[A-Z][A-Z'&.\-]*)+\b")

# A caps run carrying one of these is a *clause* the rules are supposed
# to rewrite ("THE APPLICATION IS HEREBY REJECTED"), not a name. It must
# stay unmasked so the simplification engine can reach it.
_CAPS_EXCLUDE = frozenset(
    """
    IS ARE WAS WERE BE BEEN HAS HAVE HAD HEREBY SHALL MAY MUST WILL
    ORDERED REJECTED ALLOWED GRANTED DISMISSED DIRECTED ADJOURNED LISTED
    FIXED HEARD HEARING FILED FILE SUBMIT SUBMITTED APPEAR MATTER
    APPLICATION PETITION NOTICE COSTS JUDGMENT JUDGEMENT DECREE RESERVED
    REPLY PENDING PETITIONER RESPONDENT APPLICANT ORDER PRONOUNCED PASSED
    GIVEN QUASHED REMANDED RELEASED CANCELLED EXTENDED RESTORED
    TRANSFERRED WITHDRAWN ADMITTED ACCEPTED REFUSED COMMITTED CONVICTED
    ACQUITTED NOTIFIED COMPLIED FURNISHED RECORDED CLEAR STAY
    """.split()
)

# A caps run made only of glue words has nothing of its own to preserve.
_CAPS_STOP = frozenset(
    """
    THE OF AND OR TO IN ON AT BY FOR WITH AS A AN THIS THAT VS V VERSUS
    NULL YES NO NOS ITS IT BETWEEN UNDER AFTER BEFORE
    """.split()
)

# ---------------------------------------------------------------------------
# Tokens
#
# Two stages lift a span of text out of the way and put it back
# verbatim: the rule stage (``protect_entities``), so a rewrite can
# only ever touch the words *around* a fact, and the model stage
# (``mask_for_translation``), so IndicTrans2 cannot touch the fact at
# all.
#
# The model stage is what constrains the format. IndicTrans2
# transliterates any Latin identifier it does not recognise -- a bare
# `CNR-AB12CD34EF56GH78IJ90` comes back as `सी. एन. आर. ...` -- and it
# transliterates a letter *inside* the braces as well, so a token
# carries digits only: `{10}`, `{11}`. Digits are copied through
# unchanged in both scripts, which is exactly what a number, a date
# and a name need.
#
# The index is offset above every brace-number the input already
# holds, so one of our tokens can never be confused with one of the
# reader's own: whatever the document had in braces stays where it
# was, and restoring our tokens cannot reach it.
# ---------------------------------------------------------------------------

# What the reader's own text may contain, and what we expect back from
# the model. Both script families of digit are accepted on the way in
# because IndicTrans2 is free to render `10` as `१०`.
_TOKEN_SCAN_RE = re.compile(r"[{[(<]\s*(\d+)\s*[}\])>]")
_TOKEN_OUT_RE = re.compile(r"[{[(<]\s*([0-9०-९]+)\s*[}\])>]")


def _free_offset(text: str) -> int:
    """An index space none of the document's own brace-numbers sit in."""
    used = [int(match.group(1)) for match in _TOKEN_SCAN_RE.finditer(text)]
    return (max(used) + 10) if used else 0


def _index_of(digits: str) -> int | None:
    """Read a token index the model may have written in either script."""
    try:
        return int("".join(str(unicodedata.decimal(char)) for char in digits))
    except (ValueError, TypeError):
        return None


class _TokenBook:
    """Lifts spans of text out of the way and puts them back verbatim."""

    def __init__(self, text: str):
        self.offset = _free_offset(text)
        self.values: dict[int, str] = {}

    def take(self, value: str) -> str:
        index = self.offset + len(self.values)
        self.values[index] = value
        return f"{{{index}}}"

    @property
    def slots(self) -> dict[int, str]:
        return dict(self.values)

    def restore(self, text: str) -> str:
        for index, value in self.values.items():
            text = text.replace(f"{{{index}}}", value)
        return text


# The order matters: identifiers first (so `123/2026` is taken as one
# unit and never mistaken for a date or an amount), then amounts, then
# section numbers, then dates, then the court and the people in it.
_PROTECT_ORDER = (
    ("cnr", _CNR_RE),
    ("case_number", _CASE_NO_RE),
    ("amount", _AMOUNT_RE),
    ("section", _SECTION_RE),
    ("date", _DATE_RE),
    ("court", _COURT_RE),
)

# Both name patterns, run in this order: the role announces the party,
# so `the petitioner Mr. Ramesh Kumar` gives up the name once, whole,
# rather than twice in pieces.
_NAME_PATTERNS = (_PARTY_NAME_RE, _TITLE_NAME_RE)


def _mask_names(text: str, book: _TokenBook) -> str:
    """Give up names, keep the words that introduce them.

    `Justice A. Sharma` keeps the title (which may be translated) and
    gives up only the name, so the name comes back exactly as filed;
    the same goes for `the petitioner` and the person it names.
    """

    def _take_name(match: re.Match) -> str:
        prefix = match.group(0)[: match.start("name") - match.start(0)]
        return prefix + book.take(match.group("name"))

    for pattern in _NAME_PATTERNS:
        text = pattern.sub(_take_name, text)

    return text


def protect_entities(text: str) -> tuple[str, _TokenBook]:
    """Replace every legal entity with a token no rule can match on."""
    book = _TokenBook(text)

    for _kind, pattern in _PROTECT_ORDER:
        text = pattern.sub(lambda m, b=book: b.take(m.group(0)), text)

    return _mask_names(text, book), book


# Section reference for the model stage: the *word* still reaches the
# model and comes back as `कलम` / `धारा`, which is what a Marathi
# reader needs, while the number itself is held back so it cannot drift.
_SECTION_DIGIT_RE = re.compile(
    r"((?:Sections?|Secs?\.?|Rules?|Clauses?|Articles?|Orders?)[ \t]+)"
    r"(\d+[A-Z]?(?:\([A-Za-z0-9]+\))*|[IVXLC]{1,7})(?![A-Za-z0-9])",
    re.IGNORECASE,
)


# Caps words (and nothing else) that open the document, immediately
# followed by a placeholder: `IN THE {court} ...`.
_LEADING_HEADING_RE = re.compile(
    r"^([A-Z][A-Z'&.\-]*(?:[ \t]+[A-Z][A-Z'&.\-]*)*)[ \t]+(\{)"
)


def _fold_leading_heading(text: str, book: _TokenBook) -> str:
    """Move the document's opening caps words into the placeholder after them.

    Only *caps* words qualify: they are heading material -- a court
    header, an endorsement -- that is preserved verbatim wherever it
    sits, so taking them out of the model's hands changes nothing the
    reader sees. Prose (`The matter is ...`) is never folded, because
    the model has to translate that.
    """
    lead = _LEADING_HEADING_RE.match(text)
    if lead is None:
        return text

    token = _TOKEN_SCAN_RE.match(text, lead.start(2))
    if token is None:
        return text

    index = _index_of(token.group(1))
    if index is None or index not in book.values:
        return text

    book.values[index] = f"{lead.group(1)} {book.values[index]}"
    return text[token.start() :]


def mask_for_translation(text: str) -> tuple[str, dict[int, str]]:
    """Hold back the things a translation must not be allowed to alter.

    Everything masked here is restored byte for byte after the model
    runs, so a CNR number, a case number, a sum of money, a party name
    or a court header survives in the script it was filed in.
    """
    book = _TokenBook(text)

    for _kind, pattern in _PROTECT_ORDER:
        if pattern is _SECTION_RE:
            continue  # section numbers are held back as digits only, below
        text = pattern.sub(lambda m, b=book: b.take(m.group(0)), text)

    text = _SECTION_DIGIT_RE.sub(
        lambda m, b=book: m.group(1) + b.take(m.group(2)), text
    )

    text = _mask_names(text, book)

    def _take_caps(match: re.Match) -> str:
        run = match.group(0)
        tokens = re.findall(r"[A-Z][A-Z'&.\-]*", run)
        if len(run) < 6 or not tokens:
            return run
        if any(token in _CAPS_EXCLUDE for token in tokens):
            return run
        if all(token in _CAPS_STOP for token in tokens):
            return run
        return book.take(run)

    text = _CAPS_RUN_RE.sub(_take_caps, text)

    # A heading that *opens* the document can lose its first words above
    # -- `IN THE` is pure connective, and connectives are deliberately
    # left alone -- which leaves the text handed to the model opening on
    # literal words followed by a run of placeholders. The model drops
    # that run. Folding the words into the placeholder they lead keeps
    # them (they were heading material and were never going to be
    # rendered anew) and puts the placeholders at the front, where the
    # model keeps them.
    text = _fold_leading_heading(text, book)

    return text, book.values


def restore_translation(
    translated: str, slots: dict[int, str]
) -> tuple[str, list[str]]:
    """Put the held-back spans back and report any the model dropped.

    What comes back from the model is not assumed to be what we sent:
    a token can arrive in Devanagari digits, with the braces tidied
    up, or not at all, and it can be echoed twice -- which would put
    the same date on the page twice. A token that is ours is
    replaced once, a repeated one is dropped rather than repeated,
    and anything we never sent (a brace-number of the reader's own,
    carried through untouched) is left exactly as it arrived.

    Returns the restored text and the values that are nowhere to be
    found, so the caller can try again without the mask rather than
    show a page with a missing date on it.
    """
    if not slots:
        return translated, []

    found: dict[int, int] = {}
    out: list[str] = []
    cursor = 0

    for match in _TOKEN_OUT_RE.finditer(translated):
        index = _index_of(match.group(1))

        if index is None or index not in slots:
            continue  # not ours: leave the reader's own text alone

        found[index] = found.get(index, 0) + 1

        if found[index] > 1:
            continue  # a repeated token would state a fact twice

        out.append(translated[cursor : match.start()])
        out.append(slots[index])
        cursor = match.end()

    out.append(translated[cursor:])

    missing = [slots[index] for index in slots if not found.get(index)]
    return "".join(out), missing


# ---------------------------------------------------------------------------
# Shaped retries
#
# IndicTrans2 does not keep every placeholder. Two failures are repeatable:
#
#   * a run of placeholders that *opens* the input is dropped along with the
#     fragment it sits in -- the model starts the sentence after it;
#   * a placeholder that closes the input is dropped -- nothing follows to
#     hold it in place.
#
# Both are fixed by giving the model something real to translate on either
# side of the text. A marker token is set just inside each edge, and the
# translation is cut back at the markers, so the sentence that was added
# never reaches the reader. The markers are numbered above every index the
# document itself can hold (`_TokenBook` starts above them), so they can
# never be mistaken for one of ours.
# ---------------------------------------------------------------------------

_EDGE_LEAD_IN = "Order."
_EDGE_TRAIL_IN = "Notice."


def _marker_span(translated: str, marker: int) -> tuple[int, int] | None:
    for match in _TOKEN_OUT_RE.finditer(translated):
        if _index_of(match.group(1)) == marker:
            return match.start(), match.end()
    return None


def _marker_is_free(slots: dict[int, str]) -> bool:
    # Nothing to hold back means nothing that can be lost, and no index
    # space above the document's own numbers to number a marker in.
    return bool(slots)


def with_lead_in(masked: str, slots: dict[int, str]) -> tuple[str, int] | None:
    """Put a sentence in front of the text, with a marker after it."""
    if not _marker_is_free(slots):
        return None

    marker = max(slots) + 1
    return f"{_EDGE_LEAD_IN} {{{marker}}} {masked}", marker


def with_trail_in(masked: str, slots: dict[int, str]) -> tuple[str, int] | None:
    """Put a sentence after the text, with a marker before it."""
    if not _marker_is_free(slots):
        return None

    marker = max(slots) + 1
    return f"{masked} {{{marker}}} {_EDGE_TRAIL_IN}", marker


def cut_after_marker(translated: str, marker: int) -> str | None:
    """Everything the model wrote after the marker, lead-in removed with it."""
    span = _marker_span(translated, marker)
    if span is None:
        return None
    return translated[span[1] :].lstrip()


def cut_before_marker(translated: str, marker: int) -> str | None:
    """Everything the model wrote before the marker, trail-in removed with it."""
    span = _marker_span(translated, marker)
    if span is None:
        return None
    return translated[: span[0]].rstrip()


# ---------------------------------------------------------------------------
# Sentence handling
# ---------------------------------------------------------------------------

# Periods that end a *part* of a line rather than a sentence. Anything
# with an internal dot is treated the same way, which also covers the
# `Crl.M.A.` style of case number.
_ABBREVIATIONS = frozenset(
    """
    mr mrs ms dr jr sr vs viz sec secs no nos vol pp para cl adv hon
    smt shri govt art ord st id infra supra
    """.split()
)


def sentence_spans(text: str) -> list[tuple[int, int]]:
    """Split into sentences, keeping every character exactly once.

    Deliberately conservative: a period only ends a sentence when the
    token before it is a real word (not `Sec.` or an initial) and the
    next character can start one. Getting this wrong would let a
    fallback revert half a document on the strength of `A. Sharma`.
    """
    spans: list[tuple[int, int]] = []
    start = 0

    for match in re.finditer(r"[.!?]+[\"')\]]*\s+", text):
        end = match.end()
        if end >= len(text):
            break

        token_match = re.search(r"([A-Za-z.]+)$", text[start : match.start()])
        token = token_match.group(1) if token_match else ""

        if token:
            if len(token) <= 1 or "." in token:
                continue
            if token.lower().rstrip(".") in _ABBREVIATIONS:
                continue

        nxt = text[end]
        if not (nxt.isupper() or nxt.isdigit() or nxt in "\"'([{"):
            continue

        spans.append((start, end))
        start = end

    spans.append((start, len(text)))
    return spans


# ---------------------------------------------------------------------------
# The rule engine
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Rule:
    id: str
    pattern: re.Pattern
    replacement: str
    why: str
    glossary_term: str | None = None


@lru_cache(maxsize=1)
def load_rules() -> tuple[tuple[Rule, ...], tuple[re.Pattern, ...], frozenset[str]]:
    data = json.loads(RULES_PATH.read_text(encoding="utf-8"))

    rules: list[Rule] = []
    for entry in data["phrase_rules"]:
        # Every pattern is wrapped so it can only match on word edges:
        # `hereby` must never rewrite the middle of an unrelated word,
        # and the wrapping group keeps an alternation like
        # `vis-à-vis|vis-a-vis` bound to both branches.
        rules.append(
            Rule(
                id=entry["id"],
                pattern=re.compile(
                    r"(?:(?<!\w)(?:%s)(?!\w))" % entry["pattern"], re.IGNORECASE
                ),
                replacement=entry["replacement"],
                why=entry.get("why", ""),
                glossary_term=entry.get("glossary_term"),
            )
        )

    ambiguity = tuple(
        re.compile(pattern, re.IGNORECASE)
        for pattern in data.get("ambiguity_patterns", [])
    )
    markers = frozenset(
        marker.lower() for marker in data.get("residual_markers", [])
    )

    return tuple(rules), ambiguity, markers


def _capitalise_replacement(match: re.Match, replacement: str) -> str:
    """Keep the capitalisation the original sentence had at that spot."""
    matched = match.group(0)
    first = next((char for char in matched if char.isalpha()), None)
    if first is None or not first.isupper():
        return replacement

    for index, char in enumerate(replacement):
        if char.isalpha():
            return replacement[:index] + char.upper() + replacement[index + 1 :]
    return replacement


def apply_rules(sentence: str) -> tuple[str, list[str]]:
    """Run every rule over one sentence. Returns (text, rule ids fired)."""
    rules, _ambiguity, _markers = load_rules()

    # One leading space so a lookbehind such as `(?<!court )` in the
    # `ordered that` rule still has characters to look at when the
    # sentence *starts* with the word being matched.
    work = " " + sentence
    fired: list[str] = []

    for rule in rules:
        # Bound as a default argument: `subn` calls the callback with
        # one argument, and a closure over the loop variable would be
        # the last rule by the time it ran.
        def _sub(match: re.Match, current: Rule = rule) -> str:
            # A replacement may name a part of what it matched -- `is
            # (rejected|granted|...)` becomes `has been \1`. `re.sub`
            # expands a backreference only in a *template*; the moment a
            # callback returns a string, that string is taken literally,
            # which is how `\1` reached the page as two characters.
            # Expand first, then put the capitalisation back.
            expanded = match.expand(current.replacement)
            return _capitalise_replacement(match, expanded)

        work, count = rule.pattern.subn(_sub, work)
        if count:
            fired.append(rule.id)

    return work[1:], fired


def _tidy(text: str) -> str:
    """Whitespace and punctuation damage left by the rewrites."""
    out = re.sub(r"[ \t]{2,}", " ", text)
    out = re.sub(r"[ \t]+([,.;:!?)\]])", r"\1", out)
    out = re.sub(r"([(])[ \t]+", r"(", out)
    out = re.sub(r"[ \t]+", " ", out.strip())
    # Sentence starts, after a rule has put a lowercase word there.
    out = re.sub(
        r"(^|[.!?][\"')\]]?[ \t]+)([a-z])",
        lambda m: m.group(1) + m.group(2).upper(),
        out,
        flags=re.MULTILINE,
    )
    return out


def _has_residual_marker(text: str, markers: frozenset[str]) -> bool:
    for marker in markers:
        if re.search(r"(?<!\w)" + re.escape(marker) + r"(?!\w)", text, re.IGNORECASE):
            return True
    return False


def is_ambiguous(text: str) -> bool:
    _rules, ambiguity, _markers = load_rules()
    return any(pattern.search(text) for pattern in ambiguity)


@dataclass
class SimplificationResult:
    original_text: str
    simple_english: str
    rules_applied: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def simplified(self) -> bool:
        return self.simple_english != self.original_text

    def as_dict(self) -> dict:
        return {
            "original_text": self.original_text,
            "simple_english": self.simple_english,
            "simplified": self.simplified,
            "rules_applied": list(self.rules_applied),
            "warnings": list(self.warnings),
        }


def simplify_legal_text(text: str) -> SimplificationResult:
    """Legal English in, plain English out, with the facts where they were.

    The work happens sentence by sentence so that a sentence the engine
    is not confident about can fall back to its own original wording
    without throwing away the sentences around it that simplified
    cleanly.
    """
    original = text or ""

    if not original.strip():
        return SimplificationResult(original, original)

    work = normalize_dates(original)
    masked, book = protect_entities(work)

    _rules, _ambiguity, markers = load_rules()

    pieces: list[str] = []
    fired: list[str] = []
    reverted = False

    for start, end in sentence_spans(masked):
        sentence = masked[start:end]
        simplified_sentence, sentence_rules = apply_rules(sentence)

        if _has_residual_marker(simplified_sentence, markers):
            pieces.append(sentence)
            reverted = True
            continue

        pieces.append(simplified_sentence)
        fired.extend(sentence_rules)

    restored = book.restore("".join(pieces))
    simple = _tidy(restored)

    warnings: list[str] = []
    if reverted or not simple.strip():
        warnings.append(LOW_CONFIDENCE_WARNING)
    if is_ambiguous(simple):
        warnings.append(AMBIGUITY_WARNING)

    if not simple.strip():
        simple = original

    ordered: list[str] = []
    for rule_id in fired:
        if rule_id not in ordered:
            ordered.append(rule_id)

    return SimplificationResult(
        original_text=original,
        simple_english=simple,
        rules_applied=ordered,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Post-translation checks
# ---------------------------------------------------------------------------

def _digits(text: str) -> str:
    """Every digit in `text`, as ASCII, whatever script it is written in.

    IndicTrans2 is free to render `2026` as `२०२६`. The date has still
    been preserved, so a check that only knew ASCII would be crying
    wolf on every correctly translated order.
    """
    out: list[str] = []
    for char in text:
        if char.isdigit():
            try:
                out.append(str(unicodedata.decimal(char)))
            except (ValueError, TypeError):
                continue
    return "".join(out)


def unpreserved_references(source: str, translated: str) -> list[str]:
    """Dates in the simple English that the translation does not carry.

    Identifiers (CNR, case numbers, amounts, names, section numbers)
    never reach this check: they are masked before the model runs and
    restored afterwards, so the only way one can go missing is that the
    model dropped its token -- which `restore_translation` reports.
    """
    carried = _digits(translated)
    missing: list[str] = []

    for match in _DATE_RE.finditer(source):
        value = match.group(0)
        signature = _digits(value)
        if signature and signature not in carried and value not in missing:
            missing.append(value)

    return missing

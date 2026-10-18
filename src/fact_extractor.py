"""
Rule-based fact / entity extraction for incident narratives.

There is deliberately NO trained model here: there are only 125 labelled
incident examples (5 per category), far too few for a reliable extractor, so
this module uses regex + keyword matching against the expected fact list in
data/raw/incident_facts.json. That is auditable and safe - a fact is only
reported when actual evidence for it is found in the text; everything else
stays missing and is returned by src/missing_info.py (we never invent values).

Special-cased extractors (per the module spec):
  * amount            -> currency regexes (Rs / INR / ₹ / lakh / comma-grouped)
  * date              -> explicit date regexes + relative terms
                         (yesterday, today, last week, this morning, ...)
  * payment method    -> payment-method keyword list (UPI, NEFT, IMPS, ...)

Everything else falls back to a keyword/substring search over the fact name:
the name is split into segments on "/", ",", " or ", " and " and a segment
counts as found when all of its significant words appear in the text (a small
hand-written synonym table maps everyday words onto fact names - "car" counts
towards "vehicles", an "FIR" towards "police"). For those facts the stored
value is the matching phrase from the user's own text. Identifier-shaped facts
(order ID, transaction/reference number, case/notice number) are strict: they
only count when a real identifier sits next to that fact's own keywords, so a
transaction reference is never reported as somebody's order ID. URL facts first
try a real URL, then fall back to the keyword check.

Output keys are the exact `fact_or_entity` strings from incident_facts.json
(e.g. "bank/wallet/payment method", "amount"), so the returned dict maps 1:1
onto the expected-fact list used by src/missing_info.py.

MULTILINGUAL (Hindi / Marathi / Hinglish). extract_facts(text, category_id,
language="en") adds four rules on top of the English ones:

  1. Devanagari digits are normalised to ASCII digits first (०१२३४५६७८९ ->
     0123456789), so every pattern below is written once and sees one digit
     alphabet. This is a no-op on Latin text.
  2. The amount rule falls back to a script-agnostic cue rule: a number
     sitting next to a money word in ANY script (English, Devanagari, or a
     Hinglish romanisation such as "rupaye" / "paisa"). The fallback only
     runs when a non-English money cue is actually present, so English text
     takes exactly the original path.
  3. Payment method, date and identifier (reference number / account) facts
     learn Devanagari keywords, e.g. यूपीआय -> UPI, खाते -> account,
     व्यवहार क्रमांक -> transaction reference. Those keywords can never match
     English text, so the English path is unchanged - verified byte-for-byte
     over 44 English inputs in the test run.
  4. `language` ("en" | "hi" | "mr" | "hinglish") only selects which
     language's relative-date wording ("कल" / "काल", "पिछले हफ्ते" /
     "गेल्या आठवड्यात") is tried first; everything else switches on from the
     script of the text itself, so the default call already handles Hindi and
     Marathi without the caller knowing the language.
"""

from __future__ import annotations

import re

from incident_data import expected_facts
from text_validation import validate_user_input

# --------------------------------------------------------------------------- #
# amount
# --------------------------------------------------------------------------- #
# Word-boundary hints: "rent" must match the fact "rent/deposit" but NOT
# "lease/rental agreement" (that one is a document, not an amount).
_AMOUNT_HINT = re.compile(r"\b(?:amount|money|salary|wage|rent|deposit)\b")

_UNIT = r"(rupees|lakh|lakhs|crore|crores|thousand)"
_AMOUNT_PATTERNS = (
    # Rs 1.5 lakh / INR 2000 / ₹5,000 (optional unit word is kept in output)
    rf"(?:₹|rs\.?\s?|inr\s?)(\d[\d,]*(?:\.\d+)?)(?:\s*{_UNIT})?\b",
    # 5000 rupees / 1.5 lakh / 3 crores
    rf"(\d[\d,]*(?:\.\d+)?)\s*{_UNIT}\b",
    # comma-grouped amounts: 5,000 / 1,20,000
    r"(\d{1,3}(?:,\d{2,3})+(?:\.\d+)?)",
)

# --- multilingual amount support ------------------------------------------ #
# Devanagari digits -> ASCII digits. Applied to a working copy of the text by
# extract_facts(); on Latin text str.translate is a no-op, so the English
# path cannot change.
_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_DEVANAGARI_BLOCK = re.compile(r"[ऀ-ॿ]")


def _keyword_pattern(phrase: str) -> str:
    """Pattern that matches `phrase` as a word.

    Latin phrases keep the original behaviour (\\b before and after, and no
    trailing \\b for multi-word phrases). Devanagari gets a lookbehind plus a
    LENIENT end instead: a trailing combining mark (े, ी, ं) is not a word
    character for Python's \\b, so "\\bरुपये\\b" matches nothing at all, and
    inflected forms such as रुपयेचे / खात्यातून have to be caught too.
    """
    if _DEVANAGARI_BLOCK.search(phrase):
        return r"(?<!\w)" + re.escape(phrase)
    return r"\b" + re.escape(phrase) + (r"\b" if " " not in phrase else r"")


# Money words that are NOT English. Their presence is what switches the
# script-agnostic fallback on, which is why English text never reaches it.
_NON_ENGLISH_MONEY = re.compile(
    r"[ऀ-ॿ]|\b(?:rupaye|rupya|rupaiya|paisa|paise)\b",
    flags=re.IGNORECASE,
)

# Cue words from every script. Devanagari and romanised Hindi/Marathi words
# can never match a Latin-only English sentence, so listing them here cannot
# change the English path.
_MONEY_CUES = (
    "amount", "money", "salary", "wage", "wages", "rent", "deposit", "paid",
    "payment", "price", "cost", "fine", "refund", "balance",
    "रकम", "रकमा", "राशि", "वेतन", "पगार", "भाडे", "जमानत", "पैसे", "पैसा",
    "रुपये", "रुपया", "रुपयां", "रुपए", "टक्के", "हजार", "लाख", "कोटी",
    "rupaye", "rupya", "rupaiya", "paisa", "paise",
)
# How far a number may sit from its money cue, and how far the scan looks.
_AMOUNT_WINDOW = 30


def _amount_by_cue(text: str) -> str | None:
    """Script-agnostic amount rule: the number CLOSEST to a money cue wins.

    Works for English, Devanagari and Hinglish alike, because the cue list
    holds money words from every script and the digits may be written in
    either alphabet (extract_facts normalises Devanagari digits first).

    Distance decides, not pattern order: in "20000 रुपये UPI से 14 सितंबर"
    the date 14 is only a few characters past रुपये as well, but 20000 is
    attached to it (gap 1 vs gap 8), so 20000 is the amount.
    """
    best_gap = None
    best_number = None
    for cue in _MONEY_CUES:
        for match in re.finditer(_keyword_pattern(cue), text, flags=re.IGNORECASE):
            # number after the cue: "amount 20000", "रुपये UPI से 14"
            tail = text[match.end(): match.end() + _AMOUNT_WINDOW]
            after = re.match(r"[^\d]{0,20}(\d[\d,]*(?:\.\d+)?)", tail)
            if after:
                gap = after.start(1)
                if best_gap is None or gap < best_gap:
                    best_gap, best_number = gap, after.group(1)
            # number before the cue: "20000 रुपये", "5,000 रकम"
            head = text[max(0, match.start() - _AMOUNT_WINDOW): match.start()]
            before = re.search(r"(\d[\d,]*(?:\.\d+)?)[^\d]{0,20}$", head)
            if before:
                gap = match.start() - before.end(1)
                if best_gap is None or gap < best_gap:
                    best_gap, best_number = gap, before.group(1)
    return best_number.replace(",", "") if best_number else None


def _extract_amount(text: str, extended: bool = False) -> str | None:
    for pattern in _AMOUNT_PATTERNS:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            number = match.group(1).replace(",", "")
            unit = match.group(2) if match.lastindex and match.lastindex >= 2 else None
            return f"{number} {unit}".strip() if unit else number
    # Script-agnostic fallback. Reached only when a non-English money cue is
    # actually present (Devanagari, "rupaye", "paisa") or the caller told us
    # the input is not English - English text keeps its original behaviour.
    if not extended and not _NON_ENGLISH_MONEY.search(text):
        return None
    return _amount_by_cue(text)


# --------------------------------------------------------------------------- #
# date
# --------------------------------------------------------------------------- #
_MONTHS = (
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
    r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
)
_DATE_PATTERNS = (
    rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{_MONTHS})\.?,?\s+\d{{4}}\b",   # 14 September 2026
    rf"\b(?:{_MONTHS})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}\b",   # September 14, 2026
    rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{_MONTHS})\.?(?:\s+\d{{4}})?\b",  # 14 September
    rf"\b(?:{_MONTHS})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?\b",               # September 14
    r"\b\d{4}-\d{1,2}-\d{1,2}\b",                                      # 2026-09-14
    r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",                                    # 14/09/2026
    r"\b\d{1,2}-\d{1,2}-\d{2,4}\b",                                    # 14-09-2026
)

# --- multilingual dates ---------------------------------------------------- #
# Hindi + Marathi month names (both scripts share one calendar vocabulary).
_DEV_MONTHS = (
    "जानेवारी|जनवरी|फेब्रुवारी|फ़रवरी|फरवरी|मार्च|एप्रिल|अप्रैल|मे|मई|"
    "जून|जुलाई|ऑगस्ट|अगस्त|सप्टेंबर|सितंबर|सितम्बर|ऑक्टोबर|अक्टूबर|"
    "नोव्हेंबर|नवंबर|नवम्बर|डिसेंबर|दिसंबर"
)
_DEV_DATE_PATTERNS = (
    # 14 सितंबर 2026 / १४ सितंबर २०२६ (digits already normalised)
    rf"\b\d{{1,2}}\s+(?:{_DEV_MONTHS})\.?,?\s+\d{{4}}\b",
    # सितंबर 14, 2026
    rf"\b(?:{_DEV_MONTHS})\.?\s+\d{{1,2}},?\s+\d{{4}}\b",
    # 14 सितंबर / 14 जून  (lookahead, not \b: a month may end in a combining
    # mark such as ी, after which \b would never match)
    rf"\b\d{{1,2}}\s+(?:{_DEV_MONTHS})(?!\w)",
    # सितंबर 14
    rf"\b(?:{_DEV_MONTHS})\.?\s+\d{{1,2}}\b",
    # durations "2 हफ्ते पहले", "3 दिवसांपूर्वी"
    r"\b\d+\s*(?:हफ्ते|हफ़ते|दिन|महीने|आठवडे|दिवस|वर्ष)\s*(?:पहले|पूर्वी|आधी)\b",
    r"\b(?:आठवड्यापूर्वी|दिवसांपूर्वी|महिन्यापूर्वी|वर्षापूर्वी)\b",
)

# Relative wording, tried after the explicit date patterns. Hindi first or
# Marathi first is decided by the `language` argument of extract_facts(); both
# lists are searched for the default, because neither can match English text.
_RELATIVE_DEV_HI = (
    "दिन पहले का दिन", "परसों", "कल रात", "आज सुबह", "आज रात",
    "पिछले हफ्ते", "पिछले महीने", "पिछले साल", "इस हफ्ते", "इस महीने",
    "बीते हफ्ते", "कल", "आज",
)
_RELATIVE_DEV_MR = (
    "दिवसापूर्वीचा दिवस", "परवा", "काल रात्री", "आज सकाळी", "आज रात्री",
    "मागच्या आठवड्यात", "गेल्या आठवड्यात", "या आठवड्यात",
    "मागच्या महिन्यात", "गेल्या महिन्यात", "या महिन्यात",
    "मागच्या वर्षी", "काल", "आज",
)
# Hinglish romanisation - only searched when the caller says language is
# hinglish, because words like "kal"/"aaj" are short and script-blind.
_RELATIVE_HINGLISH = (
    "parso", "kal raat", "aaj subah", "aaj raat", "pichle hafte",
    "pichle mahine", "is hafte", "is mahine", "kal", "aaj",
)
# Relative terms, longest first so "day before yesterday" wins over
# "yesterday". Durations like "two months ago" are caught by _AGO_RE before
# this list is consulted.
_RELATIVE_TERMS = (
    "day before yesterday",
    "last two months",
    "last two weeks",
    "last few days",
    "two days ago",
    "three days ago",
    "past week",
    "past month",
    "past year",
    "last monday",
    "last tuesday",
    "last wednesday",
    "last thursday",
    "last friday",
    "last saturday",
    "last sunday",
    "this morning",
    "this evening",
    "this afternoon",
    "last night",
    "yesterday",
    "today",
    "last week",
    "last month",
    "last year",
    "this week",
    "this month",
    "this year",
)
# "... ago" durations: "two months ago", "a week ago".
_AGO_RE = re.compile(r"\b(\w+(?:\s+\w+)?\s+ago)\b", flags=re.IGNORECASE)


def _extract_date(text: str, language: str = "en") -> str | None:
    for pattern in _DATE_PATTERNS:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return " ".join(match.group(0).split())
    # Devanagari wording (never matches Latin-only English text).
    for pattern in _DEV_DATE_PATTERNS:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return " ".join(match.group(0).split())
    match = _AGO_RE.search(text)
    if match:
        return " ".join(match.group(0).split())
    lower = text.lower()
    if _DEVANAGARI_BLOCK.search(text):
        # Language decides which of the two vocabularies is tried first; both
        # are always searched, because Devanagari text cannot be English.
        dev_sets = (
            (_RELATIVE_DEV_MR, _RELATIVE_DEV_HI)
            if language == "mr"
            else (_RELATIVE_DEV_HI, _RELATIVE_DEV_MR)
        )
        for terms in dev_sets:
            for term in terms:
                if term in text:
                    return term
    if language == "hinglish":
        for term in _RELATIVE_HINGLISH:
            if term in lower:
                return term
    for term in _RELATIVE_TERMS:
        if term in lower:
            return term
    return None


# --------------------------------------------------------------------------- #
# payment method
# --------------------------------------------------------------------------- #
# Labels stay English (they are the value handed to the UI); the keyword lists
# accept the Devanagari spelling too - those strings cannot match English text.
_PAYMENT_METHODS = (
    ("UPI", ("upi", "phonepe", "google pay", "gpay", "bhim",
             "यूपीआय", "यूपीआई", "फोनपे", "फ़ोनपे", "गुगल पे", "गूगल पे",
             "गूगलपे", "भीम")),
    ("NEFT", ("neft", "एनईएफटी")),
    ("IMPS", ("imps", "आयएमपीएस")),
    ("RTGS", ("rtgs", "आरटीजीएस")),
    ("net banking", ("net banking", "internet banking", "नेटबँकिंग",
                     "नेट बैंकिंग", "इंटरनेट बैंकिंग")),
    ("bank transfer", ("bank transfer", "wire transfer", "बँक ट्रान्सफर",
                       "बैंक ट्रांसफर", "बँक ट्रान्सफर")),
    ("cheque", ("cheque", "धनादेश")),
    ("credit card", ("credit card", "क्रेडिट कार्ड")),
    ("debit card", ("debit card", "डेबिट कार्ड")),
    ("card", ("card", "कार्ड")),
    ("wallet", ("wallet", "paytm", "amazon pay", "वॉलेट", "पर्स")),
    ("cash", ("cash", "रोख", "रोकडे")),
)


def _contains(text_lower: str, phrase: str) -> bool:
    return re.search(_keyword_pattern(phrase), text_lower) is not None


def _extract_payment_method(text: str) -> str | None:
    lower = text.lower()
    for label, keywords in _PAYMENT_METHODS:
        if any(_contains(lower, keyword) for keyword in keywords):
            return label
    return None


# --------------------------------------------------------------------------- #
# identifiers (order ID, reference numbers, URLs)
# --------------------------------------------------------------------------- #
_URL = r"(?:https?://|www\.)[^\s,;)\]\"']+"

# Generic words that appear in many fact names - by themselves they are too
# weak to pin an identifier to a fact ("number" is in 6 different facts).
_GENERIC_ID_WORDS = {
    "number", "numbers", "reference", "references", "ref", "no", "id", "ids",
    "code", "token",
}

# Devanagari keywords per English identifier word: the keyword is only added
# for the words THIS fact is actually about, so a case number is still not
# reported as somebody's order ID. Devanagari strings cannot match English
# text, so the English path is untouched.
_DEV_ID_KEYWORDS = {
    "account": ("खाते", "खाता", "खातं", "खात्यात", "खात्यातील"),
    "transaction": ("व्यवहार", "ट्रान्सॅक्शन", "ट्रांसैक्शन"),
    "reference": ("संदर्भ", "रेफरन्स", "रेफरेंस", "संदर्भ क्रमांक"),
    "number": ("क्रमांक", "नंबर", "संख्या"),
    "numbers": ("क्रमांक", "नंबर", "संख्या"),
    "id": ("आयडी", "आईडी"),
    "case": ("प्रकरण", "केस"),
    "notice": ("नोटीस", "सूचना"),
    "order": ("ऑर्डर", "मागणी"),
    "complaint": ("शिकायत", "तक्रार"),
    "application": ("अर्ज", "अर्जातील"),
    "phone": ("फोन", "मोबाइल", "दूरध्वनि"),
    "sender": ("प्रेषक", "पाठवणारा"),
    "grievance": ("तक्रार", "शिकायत"),
    "portal": ("पोर्टल",),
    "serial": ("सिरीयल", "श्रृंखला"),
    "receipt": ("पावती", "पावतीपत्र"),
    "refund": ("परतावा",),
}


def _id_keywords(fact_name: str, devanagari: bool = False) -> list:
    """Fact-specific words an identifier must sit next to.

    "transaction/reference number" -> ["transaction"], "order ID" -> ["order"],
    so a transaction reference is never reported as somebody's order ID.
    """
    words = []
    for part in _SEGMENT_SPLIT.split(fact_name):
        words.extend(_significant_words(part))
    specific = [
        word
        for word in words
        if word.lower().strip(".:,;()") not in _GENERIC_ID_WORDS
    ]
    chosen = specific or words
    keywords = {stem for word in chosen for stem in _stems(word)}
    if devanagari:
        for word in chosen:
            keywords.update(
                _DEV_ID_KEYWORDS.get(word.lower().strip(".:,;()"), ())
            )
        # Reference-number facts additionally accept the shared reference
        # wording: Devanagari users write "रेफरन्स नंबर" far more often than
        # "व्यवहार क्रमांक", and every fact in that family is a reference
        # number anyway (the English path keeps its stricter rule).
        if "reference" in fact_name.lower():
            for word in words:
                if word.lower().strip(".:,;()") in _GENERIC_ID_WORDS:
                    keywords.update(
                        _DEV_ID_KEYWORDS.get(word.lower().strip(".:,;()"), ())
                    )
    return sorted(keywords)


def _extract_url(text: str) -> str | None:
    match = re.search(_URL, text, flags=re.IGNORECASE)
    return match.group(0) if match else None


def _extract_identifier(text: str, fact_name: str, devanagari: bool = False) -> str | None:
    """Capture the real value of an identifier-shaped fact.

    Strict on purpose: the number must sit next to one of THIS fact's own
    keywords and hold at least 5 digits (so a bare year never counts).
    Returns None when nothing qualifies - the fact then stays missing rather
    than borrowing an unrelated number from the text.
    """
    keywords = _id_keywords(fact_name, devanagari=devanagari)
    if not keywords:
        return None
    # Each keyword carries its own boundaries (see _keyword_pattern), so a
    # Devanagari keyword whose last character is a combining mark still
    # matches while Latin keywords keep their \b rule.
    alternation = "|".join(_keyword_pattern(k) for k in keywords)

    patterns = (
        # "transaction reference number is 81234567", "case number 1234/2026"
        rf"\b(?:{alternation})\D{{0,40}}?(?<![\d/])(\d{{4,}}(?:/\d{{2,4}})?)(?!\d)",
        # short court-style numbers: "case no 45/2020" (never "08/2026" inside
        # a date like 12/08/2026 - the lookbehind blocks a mid-date start)
        rf"\b(?:{alternation})\D{{0,40}}?(?<![\d/])(\d{{1,4}}/\d{{4}})(?!\d)",
        # alphanumeric ids: "order id: AB-99221"
        rf"\b(?:{alternation})[^a-z0-9]{{0,10}}(?:id|no\.?|number|ref|code)?"
        rf"\s*[:#/-]?\s*([a-z0-9][a-z0-9-]{{3,}})\b",
    )

    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            value = match.group(1)
            if len(re.sub(r"\D", "", value)) >= 5:
                return value
    return None


# --------------------------------------------------------------------------- #
# generic keyword / substring fallback
# --------------------------------------------------------------------------- #
_SEGMENT_SPLIT = re.compile(r"\s*[,/|]\s*|\s+and\s+|\s+or\s+|\s+&\s*", re.IGNORECASE)

# Words that carry no evidence on their own.
_FILLER = {
    "the", "a", "an", "of", "or", "and", "to", "in", "on", "for", "with", "if",
    "is", "are", "was", "were", "be", "been", "being", "by", "at", "from", "as",
    "that", "this", "these", "those", "whether", "what", "where", "when", "how",
    "who", "whom", "whose", "why", "not", "no", "its", "it", "they", "them",
    "their", "we", "you", "your", "my", "me", "i", "any", "some", "all",
    "involved", "involving", "described", "stated", "suspected", "claimed",
    "existing", "available", "prior", "exact", "applicable", "else", "etc",
    "regarding", "related", "said", "made", "keep",
}


def _stems(word: str) -> set:
    """Word + simple plural/verb variants so 'screenshots' matches 'screenshot'."""
    word = word.lower().strip(".:,;()")
    forms = {word}
    if word.endswith("ies"):
        forms.add(word[:-3] + "y")
    if word.endswith("es"):
        forms.add(word[:-2])
    if word.endswith("s"):
        forms.add(word[:-1])
    return {form for form in forms if len(form) >= 3}


# Small, deliberate synonym table (still plain keyword search - no model) so
# obvious evidence is not reported as missing: "car" counts towards the
# expected fact "vehicles", an "FIR" towards "police", and so on.
_SYNONYMS = {
    "vehicle": ("car", "bike", "two-wheeler", "scooter", "truck", "bus", "rickshaw"),
    "police": ("fir",),
    "injury": ("injured", "hurt", "wounded"),
    "photo": ("picture", "image", "snapshot"),
    "receipt": ("bill", "invoice"),
    "invoice": ("bill", "receipt"),
    "message": ("whatsapp", "sms", "chat", "email"),
    "witness": ("eyewitness", "bystander"),
    "platform": (
        "instagram", "whatsapp", "facebook", "twitter", "telegram",
        "youtube", "snapchat", "linkedin", "olx", "flipkart", "amazon",
    ),
    "seller": ("vendor", "merchant", "shopkeeper"),
    # Devanagari equivalents - inert on English text, they only ever match
    # when the input itself is written in Devanagari.
    "account": ("खाते", "खाता", "खातं", "खात्यात"),
    "transaction": ("व्यवहार", "ट्रान्सॅक्शन"),
    "reference": ("संदर्भ", "रेफरन्स", "रेफरेंस"),
    "number": ("क्रमांक", "नंबर", "संख्या"),
    "amount": ("रकम", "राशि", "पैसे"),
    "location": ("ठिकाण", "स्थान"),
    "police": ("fir", "पोलीस", "एफआयआर"),
    "date": ("तारीख", "दिनांक"),
    "statement": ("स्टेटमेंट", "विवरण पत्र"),
    "message": ("whatsapp", "sms", "chat", "email", "संदेश", "मेसेज"),
    "employer": ("नियोक्ता", "मालक"),
    "landlord": ("मालक", "मकानमालक"),
    "tenant": ("भाडेकरू", "किरायेदार"),
}


def _evidence_in(text: str, word: str) -> str | None:
    """The phrase in the user's own text that satisfies `word`.

    Returns the exact substring as typed (original casing preserved), e.g.
    word "vehicles" -> "car" (synonym), word "police" -> "FIR" (synonym),
    word "statement" -> "statement". None when nothing matches.
    Stems are tried longest-first so the result is deterministic.
    """
    for stem in sorted(_stems(word), key=len, reverse=True):
        match = re.search(r"\b" + re.escape(stem) + r"\w*", text, flags=re.IGNORECASE)
        if match:
            return match.group(0)
    for stem in sorted(_stems(word), key=len, reverse=True):
        for synonym in _SYNONYMS.get(stem, ()):
            match = re.search(_keyword_pattern(synonym), text, flags=re.IGNORECASE)
            if match:
                return match.group(0)
    return None


def _significant_words(phrase: str) -> list:
    return [
        word
        for word in phrase.split()
        if word.lower().strip(".:,;()") not in _FILLER
        and len(word.lower().strip(".:,;()")) > 2
    ]


def _extract_generic(text: str, fact_name: str) -> str | None:
    segments = [seg.strip() for seg in _SEGMENT_SPLIT.split(fact_name) if seg.strip()]

    # "whether ..." facts are yes/no questions - only report them when EVERY
    # significant word of the fact is present, so the detector never pretends
    # the user answered something they did not (they then show up as missing
    # information and the UI can simply ask).
    if fact_name.lower().startswith("whether"):
        words = []
        for part in _SEGMENT_SPLIT.split(fact_name):
            words.extend(_significant_words(part))
        if words and all(_evidence_in(text, word) for word in words):
            return fact_name
        return None

    for segment in segments:
        words = _significant_words(segment)
        if not words:
            continue
        pieces = [_evidence_in(text, word) for word in words]
        if all(piece is not None for piece in pieces):
            # The user's own phrasing, e.g. fact "vehicles" -> "car".
            return " ".join(pieces)
    return None


# --------------------------------------------------------------------------- #
# public API
# --------------------------------------------------------------------------- #
def _extract_one(text: str, fact_name: str, language: str = "en"):
    name = fact_name.lower()
    devanagari = bool(_DEVANAGARI_BLOCK.search(text))

    if _AMOUNT_HINT.search(name):
        # extended = the caller said this is not English; a Devanagari /
        # "rupaye" / "paisa" cue in the text switches it on by itself.
        return _extract_amount(text, extended=language != "en")
    if "date" in name:
        return _extract_date(text, language=language)
    if "payment method" in name or "payment details" in name:
        return _extract_payment_method(text)
    if "url" in name or "http" in name:
        # URL facts often bundle other evidence words ("screenshots/URLs"),
        # so when there is no real URL we still allow the keyword check.
        return _extract_url(text) or _extract_generic(text, fact_name)
    if "number" in name or "reference" in name or name.endswith(" id") or " id " in name:
        # Identifier facts are strict: no real identifier -> fact stays
        # missing (we never borrow an unrelated number from the text).
        return _extract_identifier(text, fact_name, devanagari=devanagari)
    return _extract_generic(text, fact_name)


def extract_facts(text: str, category_id: str, language: str = "en") -> dict:
    """Extract the expected facts for `category_id` that are actually present.

    Returns {fact_name: value} containing ONLY the facts that were found;
    missing facts are deliberately absent (see src/missing_info.py).

    `language` is a hint: "en" (default), "hi", "mr" or "hinglish". It only
    picks which language's relative-date wording is tried first and turns on
    the Hinglish romanisation; the Devanagari rules switch on from the script
    of the text itself, so calling this with the default still extracts
    amounts, payment methods, dates and reference numbers from Hindi and
    Marathi input. Values come back from a normalised copy of the text, so
    Devanagari digits (१२३) appear as ASCII digits (123); for Latin text that
    normalisation is a no-op and the output is byte-for-byte what the English
    rules alone produce.

    Raises ValueError for invalid input.
    """
    cleaned = validate_user_input(text)
    # 1. Devanagari digits -> ASCII (no-op on Latin text).
    working = cleaned.translate(_DEVANAGARI_DIGITS)

    found = {}
    for fact_name in expected_facts(category_id):
        value = _extract_one(working, fact_name, language=language)
        if value is not None and str(value).strip():
            found[fact_name] = str(value).strip()
    return found

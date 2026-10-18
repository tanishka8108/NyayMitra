"""
WHAT HAPPENED? — NyayMitra case & incident companion.

The orchestration behind POST /api/what-happened. Two modes:

  incident   somebody describes something that happened to them and
             wants to understand what it may indicate, what to keep,
             and what they can consider doing next;

  case       somebody with a case already running asks what happened
             or what to do next, answered only from the case record
             they sent with the question.

Design rules this module exists to enforce:

  * Nothing is invented. No legal sections, no dates, no deadlines,
    no evidence, no court outcomes, no reasons for adjournments. When
    the record does not state something, the answer says so.
  * Everything that needs a model (translation) or a record (the case
    snapshot) is passed in as a callable or a plain dict, so this file
    imports nothing heavier than the JSON guidance and glossary files.
    That is what lets the tests run on a machine with no checkpoints.
  * Reuse: next-step guidance comes from the existing guidance set via
    `guidance_match.match_guidance` (incident) and
    `next_steps_guidance_lookup.get_next_steps` (case stage), and legal
    terms are read through the existing glossary.

Field contract shared by both modes (extra fields are simply empty for
the mode that does not use them):

    mode, language, conversation_id, acknowledgement,
    summary, possible_issue, explanation,
    case_facts, record_gaps,
    next_steps, preserve_information, follow_up_questions, warnings,
    time_sensitive, time_sensitivity_note,
    matched_stage, guidance, legal_terms, disclaimer,
    interpretation_source

`interpretation_source` says who produced the reading:

    "placeholder_template"  rule-based placeholder (Member 2's model
                            unconnected or unusable — the response
                            also carries PLACEHOLDER_HEDGE in its
                            warnings, so the reading is never
                            mistaken for final model output)
    "member2_model"         Member 2's interpretation model produced
                            summary/possible_issue/explanation
    "record_grounded"       case mode: the reading came from the case
                            record, not from any interpretation model

The model-facing seam itself lives in `what_happened_interpretation`
and is documented in API_member2_interpretation.md.
"""

import re
import threading
import uuid
from datetime import date as _date

from guidance_match import glossary_terms_for, match_guidance
from next_steps_guidance_lookup import get_next_steps
from what_happened_interpretation import (
    MODEL_FIELDS,
    MODEL_FIELDS_KEY,
    PLACEHOLDER_HEDGE,
    SOURCE_MODEL,
    SOURCE_PLACEHOLDER,
    SOURCE_RECORD,
    interpret,
)

SUPPORTED_LANGUAGES = ("en", "hi", "mr")
SUPPORTED_MODES = ("incident", "case")

DISCLAIMER = (
    "This is general legal information and not a substitute for "
    "advice from a qualified legal professional."
)

# Long inputs are read in full for detection but only the head is ever
# quoted back, so one paste of a whole judgment cannot blow up a reply.
MAX_TEXT_CHARS = 6000
MAX_QUOTE_CHARS = 400


# ---------------------------------------------------------------------------
# FACT PROTECTION
#
# Dates, CNR numbers, case numbers, section numbers and amounts must
# survive translation byte-for-byte. Each such span is swapped for a
# short token before translation and swapped back afterwards. If the
# translator swallows a token anyway, the field falls back to English
# rather than returning a sentence whose numbers have drifted.
# ---------------------------------------------------------------------------

_PROTECTED_PATTERNS = [
    # CNR — four to six letters then a long digit run (PBASB00008022024).
    r"\b[A-Z]{4,6}\d{9,12}\b",
    # 5th October 2026 / October 5, 2026
    r"\b\d{1,2}(?:st|nd|rd|th)?\s+(?:January|February|March|April|May|June"
    r"|July|August|September|October|November|December)\s+\d{4}\b",
    r"\b(?:January|February|March|April|May|June|July|August|September"
    r"|October|November|December)\s+\d{1,2},?\s+\d{4}\b",
    # 2026-10-06 and 06/10/2026
    r"\b\d{4}-\d{2}-\d{2}\b",
    r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
    # Filing and registration numbers — 790/2024
    r"\b\d{1,7}/\d{4}\b",
    # Section references — Section 148, Sections 324, 326, Order 21 Rule 11
    r"\bSections?\s+\d+[A-Za-z]*(?:\s*,\s*\d+[A-Za-z]*)*\b",
    r"\bOrder\s+\d+\s+Rule\s+\d+\b",
    r"\b(?:IPC|BNS|CrPC|BNSS|IEA|IT Act)\s+\d+[A-Za-z]*(?:\s*,\s*\d+[A-Za-z]*)*\b",
    r"\b\d{2,4}(?:\s*,\s*\d{2,4}){1,6}\b",
    # Money — Rs. 5,000 / ₹2500 / INR 1,000.50
    r"\b(?:Rs\.?|INR|₹)\s*\d[\d,]*(?:\.\d+)?\b",
]

_PROTECTED_RE = re.compile(
    "|".join(f"(?:{pattern})" for pattern in _PROTECTED_PATTERNS)
)

_TOKEN_RE_TEMPLATE = r"N\s*M\s*{index}\s*X"


class FactPreservationError(Exception):
    """A protected span did not survive translation."""

    def __init__(self, missing):
        self.missing = list(missing)
        super().__init__(
            "protected spans lost in translation: " + ", ".join(self.missing)
        )


def extract_protected_spans(text: str) -> list:
    """Every fact the translation must not alter, in first-seen order."""
    seen = []
    for match in _PROTECTED_RE.finditer(text or ""):
        value = match.group(0)
        if value not in seen:
            seen.append(value)
    return seen


def mask_protected_spans(text: str, spans: list) -> str:
    """Swap each span for NM<i>X, longest first so overlaps do not bite."""
    masked = text
    for index, span in sorted(
        enumerate(spans), key=lambda item: len(item[1]), reverse=True
    ):
        masked = masked.replace(span, f"NM{index}X")
    return masked


def unmask_protected_spans(translated: str, spans: list) -> tuple:
    """(text, missing). Tokens are matched loosely because a model may
    re-space them; a token that is simply gone lands in `missing`."""
    restored = translated or ""
    missing = []

    for index, span in enumerate(spans):
        token = re.compile(
            _TOKEN_RE_TEMPLATE.format(index=index), flags=re.IGNORECASE
        )
        restored, count = token.subn(lambda _m, value=span: value, restored)
        if count == 0:
            missing.append(span)

    return restored, missing


def translate_preserving_facts(text: str, translator, language: str) -> str:
    """Translate one field, or raise FactPreservationError.

    `translator` is `translator(text, language) -> str`; the endpoint
    passes the IndicTrans2-backed one, tests pass a fake.
    """
    spans = extract_protected_spans(text)

    if not spans:
        return translator(text, language)

    translated = translator(mask_protected_spans(text, spans), language)
    restored, missing = unmask_protected_spans(translated, spans)

    if missing:
        raise FactPreservationError(missing)

    return restored


# ---------------------------------------------------------------------------
# INCIDENT CATEGORIES
#
# Signals are matched as substrings against what the person wrote, in
# English and Devanagari, so a Hindi or Marathi account reaches the same
# category as the English one. The `issue` wording always hedges —
# "may indicate" — and never cites a numeric section, because which
# provisions apply is a question for an advocate and the facts.
# ---------------------------------------------------------------------------

_INCIDENT_CATEGORIES = [
    {
        "id": "otp_bank_fraud",
        "label": "Possible financial fraud through an impersonated call or message",
        "signals": [
            "otp", "one time password", "one-time password",
            "pretending to be from my bank", "pretending to be my bank",
            "from my bank", "bank called", "called me claiming",
            "kyc", "debit card", "credit card", "upi",
            "money deducted", "amount deducted", "amount was deducted",
            "money was deducted", "phishing", "impersonat",
            "fraudulent call", "fake call", "posing as",
            "ओटीपी", "बैंक", "धोखे से पैसे", "रुपये कट", "पैसे कटे",
            "क्रेडिट कार्ड", "डेबिट कार्ड", "यूपीआई", "धोखाधड़ी",
            # Marathi spellings of the same signals.
            "बँक", "पैसे कापले", "रक्कम कापली", "धोका",
        ],
        "issue": (
            "Based on what you described, this may indicate a financial "
            "fraud in which someone impersonated your bank or another "
            "trusted caller and obtained information that let money "
            "leave your account. Impersonation and cheating for gain "
            "are treated as offences under Indian law, but the exact "
            "provisions depend on the facts and should be confirmed by "
            "a qualified lawyer."
        ),
        "preserve": [
            "Call records: the number that contacted you, with date and time",
            "SMS or chat messages you received, including any link or OTP message",
            "Bank statement lines showing the deduction and the transaction reference",
            "The complaint or reference number your bank gave you, if any",
            "A short written note of what was said and when",
        ],
        "next_steps": [
            "Tell your bank at once through its official helpline or branch and ask whether the transaction can be recalled or the card blocked",
            "Report it on the national cybercrime portal or the cyber fraud helpline (1930) — the earlier a transaction is reported, the better the chance of recovery",
            "Note down whom you reported it to, and when",
        ],
        "follow_ups": [
            "When did this happen, and how much money was deducted?",
            "Do you still have the calls, messages or the number that contacted you?",
            "Have you already told your bank or the police, and what did they say?",
        ],
    },
    {
        "id": "cyber_fraud",
        "label": "Possible online or cyber fraud",
        "signals": [
            "online", "website", "whatsapp", "instagram", "facebook",
            "email", "fake link", "link", "hacked", "hacker",
            "cyber", "social media", "scammed", "online fraud",
            "fake account", "olx", "meesho", "amazon", "flipkart",
            "साइबर", "ऑनलाइन", "लिंक", "वेबसाइट", "हैक", "धोखा",
        ],
        "issue": (
            "Based on what you described, this may indicate an online "
            "fraud — someone using the internet or a messaging app to "
            "deceive you. Cyber offences and cheating are recognised "
            "under Indian law; the provisions that apply depend on how "
            "it was done and should be confirmed by a lawyer."
        ),
        "preserve": [
            "The profile, page, link or website address involved",
            "Screenshots of the messages, with the date and time visible",
            "Payment records or transaction references",
            "Any user ID, phone number or name the other side used",
        ],
        "next_steps": [
            "Stop all contact with the other side and do not send more money or information",
            "Report the matter to the platform and to the cybercrime portal or helpline (1930)",
            "Ask your bank to flag the transaction if money has already moved",
        ],
        "follow_ups": [
            "Which app, site or number was involved?",
            "Was any money or personal information given, and how much?",
            "Do you have screenshots of the conversation?",
        ],
    },
    {
        "id": "threat_extortion",
        "label": "Possible threat, intimidation or extortion",
        "signals": [
            "threat", "threaten", "threatened", "demanding money",
            "demanded money", "demanded that", "ransom", "blackmail",
            "extort", "intimidat", "will harm", "harm you", "attack you",
            "धमकी", "धमकाया", "पैसे की मांग", "ब्लैकमेल", "नुकसान करने",
        ],
        "issue": (
            "Based on what you described, this may indicate a threat or "
            "extortion — a demand backed by intimidation. Criminal "
            "intimidation and extortion are recognised offences; which "
            "provisions apply depends on what was said, by whom, and "
            "how, and should be confirmed by a lawyer."
        ),
        "preserve": [
            "The messages, letters or recordings of the threat, unchanged",
            "Who said it — name, number, handle or description",
            "When and where each contact happened",
            "Names of anyone who heard or saw it",
        ],
        "next_steps": [
            "Do not delete anything and do not respond with more money or promises",
            "If you are in immediate danger, call 112; otherwise consider informing the police",
            "Speak to an advocate about the threat before the other side escalates it",
        ],
        "follow_ups": [
            "Was the threat spoken, written, or sent as a message?",
            "What exactly was demanded, and by when?",
            "Are you or anyone with you in immediate danger right now?",
        ],
    },
    {
        "id": "cheating_fraud",
        "label": "Possible cheating or fraud",
        "signals": [
            "cheated", "cheat", "cheating", "fraud", "fraudster",
            "defraud", "took my money", "took the money", "scam",
            "promised and", "fake receipt", "duped",
            "धोखा", "धोखाधड़ी", "पैसे लेकर भाग", "नकली",
        ],
        "issue": (
            "Based on what you described, this may indicate cheating — "
            "being deceived into parting with money or property. "
            "Cheating is a recognised offence, but whether it applies "
            "here depends on how the deception was proved and should be "
            "confirmed by a lawyer."
        ),
        "preserve": [
            "Any agreement, receipt, message or note of what was promised",
            "Payment records — bank transfer, UPI or cash acknowledgment",
            "The other side's name, number and address as you know them",
        ],
        "next_steps": [
            "Write down the sequence of events with dates while they are fresh",
            "Keep the originals of anything you hand over to the police or an advocate",
            "Consider a police complaint or a civil claim after speaking to an advocate",
        ],
        "follow_ups": [
            "What was promised, and what was actually given?",
            "How was the payment made, and can you prove it?",
            "Do you know where the other person can be found?",
        ],
    },
    {
        "id": "theft",
        "label": "Possible theft or robbery",
        "signals": [
            "stole", "stolen", "theft", "robbed", "robbery",
            "burglary", "snatched", "pickpocket", "missing from",
            "चोरी", "चोर", "लूट", "छीन",
        ],
        "issue": (
            "Based on what you described, this may indicate theft or "
            "robbery — property taken without consent. Which offence "
            "this amounts to depends on how it happened and should be "
            "confirmed by a lawyer."
        ),
        "preserve": [
            "A list of what was taken, with values if you know them",
            "Bill, invoice or photograph of the property",
            "CCTV footage or witness names, if any exist nearby",
            "The First Information Report number, once a complaint is filed",
        ],
        "next_steps": [
            "Report the theft to the police promptly — a delay is often questioned later",
            "Ask for the FIR or a written acknowledgement of your complaint",
            "Claim under insurance, if the property was insured, with the policy papers",
        ],
        "follow_ups": [
            "When and where did it happen?",
            "What exactly was taken, and do you have proof you owned it?",
            "Did anyone see it happen, or is there a camera nearby?",
        ],
    },
    {
        "id": "assault",
        "label": "Possible assault or hurt",
        "signals": [
            "hit me", "hit ", "beat", "beaten", "assault", "attacked",
            "attack", "injured", "injury", "hurt me", "broke my",
            "weapon", "sticks", "किया ", "मारपीट", "पीटा", "चोट",
            "घायल", "मारना", "मारले", "इजा",
        ],
        "issue": (
            "Based on what you described, this may indicate an assault "
            "causing hurt. The offence and its seriousness depend on "
            "the injuries and how it happened, and should be confirmed "
            "by a lawyer and, where relevant, a medical examination."
        ),
        "preserve": [
            "Any medical report or prescription from the treatment taken",
            "Photographs of injuries, dated",
            "Names and contact details of witnesses",
            "The clothes or objects involved, if they can be kept",
        ],
        "next_steps": [
            "Get medical treatment first, and keep every report and bill",
            "Consider a police complaint the same day if you feel safe doing so",
            "Speak to an advocate about the medical-legal documentation",
        ],
        "follow_ups": [
            "Are you safe right now, and did you need medical care?",
            "Who was present when it happened?",
            "Was any weapon involved?",
        ],
    },
    {
        "id": "harassment",
        "label": "Possible harassment or stalking",
        "signals": [
            "harass", "harassment", "abusive", "abused", "stalking",
            "stalker", "obscene", "following me", "keeps calling",
            "nuisance", "परेशान", "उत्पीड़न", "पीछा", "अश्लील", "गाली",
            "त्रास", "उत्पीडन",
        ],
        "issue": (
            "Based on what you described, this may indicate harassment "
            "or stalking. Whether it is a criminal matter depends on "
            "what was done and said, and should be confirmed by a "
            "lawyer."
        ),
        "preserve": [
            "Messages, calls and their timings, unaltered",
            "Screenshots showing the sender's identity",
            "Any previous complaint you have made about the same person",
        ],
        "next_steps": [
            "Do not engage further; keep the evidence instead",
            "Consider a police complaint or a protective application through an advocate",
            "Tell someone you trust about the pattern of contact",
        ],
        "follow_ups": [
            "How long has this been happening, and how often?",
            "Do you know the person doing this?",
            "Have you asked them to stop, or complained anywhere before?",
        ],
    },
    {
        "id": "domestic_dowry",
        "label": "Possible domestic cruelty or dowry-related harassment",
        "signals": [
            "dowry", "husband", "wife", "in-laws", "inlaws",
            "in laws", "domestic violence", "married life",
            "sasural", "maintenance from",
            "दहेज", "ससुराल", "पति", "पत्नी", "घरेलू हिंसा", "शादी",
        ],
        "issue": (
            "Based on what you described, this may indicate cruelty or "
            "harassment within the family, including possible dowry-"
            "related harassment. Family-law remedies exist for this; "
            "which one fits should be confirmed by a lawyer."
        ),
        "preserve": [
            "Messages, calls or letters showing what was said or demanded",
            "Any complaint already made to a women's help line or police",
            "Details of where you both live and any financial support given",
        ],
        "next_steps": [
            "If you are in immediate danger, call 112; the women's helpline (181) also takes calls",
            "Keep every message and record — family matters are decided on what can be shown",
            "Speak to a lawyer or a legal aid organisation about protection and maintenance options",
        ],
        "follow_ups": [
            "Are you safe where you are right now?",
            "Was anything demanded in money or property, and do you have it recorded?",
            "Have you approached any helpline, police station or lawyer before?",
        ],
    },
    {
        "id": "property_rent",
        "label": "Possible property or tenancy dispute",
        "signals": [
            "landlord", "tenant", "rent", "evict", "eviction",
            "possession", "property", "flat", "shop", "lease",
            "vacate", "मकान", "किराया", "मालिक", "जायदाद", "खाली",
            "भाड्याने", "मालक", "संपत्ती",
        ],
        "issue": (
            "Based on what you described, this may indicate a landlord "
            "and tenant or property dispute. These are usually decided "
            "on the agreement, the rent control law that applies in "
            "your area, and the notices exchanged — a lawyer can say "
            "which applies."
        ),
        "preserve": [
            "The rent agreement or sale deed, in original",
            "Rent receipts and records of payments",
            "Every notice or letter exchanged, with dates",
            "Photographs of the property's condition, if relevant",
        ],
        "next_steps": [
            "Read the agreement clause on notice period and termination before replying",
            "Answer any notice in writing and keep proof that you sent it",
            "Take advice before stopping payment or changing locks",
        ],
        "follow_ups": [
            "Do you have a written agreement, and what does it say about notice?",
            "Has any notice been served, and when does it take effect?",
            "Is possession of the property being disputed?",
        ],
    },
    {
        "id": "consumer_deficiency",
        "label": "Possible consumer dispute",
        "signals": [
            "warranty", "guarantee", "refund", "defective", "damaged",
            "product", "seller", "shopkeeper", "consumer",
            "not delivered", "service not", " cheating from store",
            "वारंटी", "रिफंड", "उपभोक्ता", "खराब", "वापस", "परतावा",
        ],
        "issue": (
            "Based on what you described, this may indicate a consumer "
            "dispute over a product or service that was not as "
            "promised. Consumer fora hear such claims; whether yours "
            "fits, and on what value, should be confirmed by a lawyer."
        ),
        "preserve": [
            "The bill, invoice or order confirmation",
            "Warranty or guarantee card and its terms",
            "Photographs of the defect or damage",
            "Every complaint you have already made, and the replies",
        ],
        "next_steps": [
            "Put the complaint in writing to the seller or manufacturer and keep the proof",
            "Calculate the value of what you paid, with documents, before filing anything",
            "Speak to a lawyer about the consumer forum your claim belongs in",
        ],
        "follow_ups": [
            "What was bought, when, and for how much?",
            "Have you already complained in writing, and what was replied?",
            "Is the product or the payment still with the seller?",
        ],
    },
    {
        "id": "road_accident",
        "label": "Possible road accident claim",
        "signals": [
            "accident", "crash", "collision", "hit and run",
            "ran over", "two wheeler", "truck hit", "car hit",
            "traffic police", "insurance claim",
            "दुर्घटना", "टक्कर", "बाइक", "कार", "एम्बुलेंस",
        ],
        "issue": (
            "Based on what you described, this may indicate a road "
            "accident with possible criminal and insurance "
            "consequences. Compensation and criminal liability are "
            "separate questions, and both should be confirmed by a "
            "lawyer."
        ),
        "preserve": [
            "The FIR or police note about the accident, if one was made",
            "Medical records, bills and discharge summary",
            "Vehicle papers, driving licence and insurance policy",
            "Photographs of the spot and the vehicles",
        ],
        "next_steps": [
            "Complete the medical treatment first and keep every document",
            "Inform the insurer within the time the policy allows",
            "Speak to an advocate about both the claim and any police case",
        ],
        "follow_ups": [
            "Was anyone injured, and have they been treated?",
            "Was the police informed, and is there an FIR or note?",
            "Do you know the registration or other details of the other vehicle?",
        ],
    },
    {
        "id": "labour_wages",
        "label": "Possible wage or employment dispute",
        "signals": [
            "salary", "wages", "employer", "fired", "terminated",
            "without notice", "unpaid", "gratuity", "pf ", "labour",
            "factory", "did not pay", "has not paid",
            "वेतन", "मजदूरी", "नौकरी", "श्रम", "भुगतान नहीं", "पगार",
        ],
        "issue": (
            "Based on what you described, this may indicate an "
            "employment or wage dispute — unpaid dues or a "
            "termination. Labour forums and civil claims can both "
            "apply, and a lawyer can say which one fits your facts."
        ),
        "preserve": [
            "Appointment letter, contract or offer mail",
            "Salary slips, bank credits and record of unpaid months",
            "Any termination or resignation letter",
            "Messages about the dues with dates",
        ],
        "next_steps": [
            "Calculate the dues you claim, month by month, with documents",
            "Send a written demand to the employer and keep the proof",
            "Speak to a labour or civil advocate about the forum that applies",
        ],
        "follow_ups": [
            "How many months of dues are pending, and how much?",
            "Do you have an appointment letter or salary slips?",
            "Was the exit voluntary, or were you asked to leave?",
        ],
    },
    {
        "id": "family_dispute",
        "label": "Possible family-law dispute",
        "signals": [
            "divorce", "maintenance", "custody", "separation",
            "judicial separation", "alimony", "visitation",
            "तलाक", "भरण", "हकदारी", "बच्चों की",
        ],
        "issue": (
            "Based on what you described, this may indicate a family "
            "dispute about separation, maintenance or custody. These "
            "are decided on statute and the welfare of any child "
            "involved, and should be handled through a lawyer."
        ),
        "preserve": [
            "Marriage certificate or photographs of the marriage",
            "Any notice, agreement or order already exchanged",
            "Records of financial support actually given or received",
        ],
        "next_steps": [
            "Keep every written communication — family courts rely on it",
            "Collect financial details of both sides as far as you can",
            "Approach a lawyer or legal aid clinic before agreeing to anything",
        ],
        "follow_ups": [
            "Is there a child living with either of you?",
            "Has any notice, agreement or order already been passed?",
            "Is any financial support being paid at present?",
        ],
    },
    {
        "id": "police_custody",
        "label": "Possible police, arrest or bail matter",
        "signals": [
            "arrest", "arrested", "police", "custody", "bail", "fir",
            "station house", "remand", "notice from police",
            "गिरफ्तार", "पुलिस", "जमानत", "एफआईआर", "थाना", "हिरासत",
            "पोलीस", "जामीन",
        ],
        "issue": (
            "Based on what you described, this may indicate a criminal "
            "procedure matter — a complaint, an arrest or a bail "
            "question. These move on fixed clocks, and the exact "
            "position should be confirmed by a lawyer without delay."
        ),
        "preserve": [
            "Any notice, order or bail paper served on you, in original",
            "The FIR number and the station it was filed at",
            "Contact details of the advocate you instruct",
        ],
        "next_steps": [
            "If someone is in custody, contact a lawyer immediately — bail applications are time-bound",
            "Keep the FIR number and every paper served on you",
            "Do not sign or record any statement without legal advice",
        ],
        "follow_ups": [
            "Has anyone been arrested, and are they in custody now?",
            "Is there an FIR number or a written notice?",
            "Have you already engaged a lawyer?",
        ],
    },
    {
        "id": "defamation",
        "label": "Possible defamation",
        "signals": [
            "defam", "false statement", "reputation", "circulating",
            "posted about me", "spread rumours", "rumours about",
            "लांछन", "बदनामी", "अफवाह", "झूठ",
        ],
        "issue": (
            "Based on what you described, this may indicate defamation "
            "or the circulation of false statements about you. Both "
            "civil and criminal routes exist; what can be proved about "
            "the words and their publication decides the rest, and a "
            "lawyer should assess it."
        ),
        "preserve": [
            "Screenshots of the words as published, with the source visible",
            "Who published them and to what audience",
            "Any witness who saw or heard it",
        ],
        "next_steps": [
            "Capture and keep the material before it is deleted",
            "Note the date, source and reach of each publication",
            "Take advice early — limitation periods apply",
        ],
        "follow_ups": [
            "Where were the words published, and to whom?",
            "Can you prove who said or posted them?",
            "Has it been removed or edited since?",
        ],
    },
]

# Enough of a signal to name a category. Below this the reply says
# plainly that the description is too thin to place.
_MIN_CATEGORY_SCORE = 2

_GENERIC_PRESERVE = [
    "A dated written account of what happened, in your own words",
    "Any message, call record, receipt or document connected to it",
    "Names and contact details of anyone who saw or heard it",
    "Any complaint reference number you have already been given",
]

_GENERIC_NEXT_STEPS = [
    "Write down what happened with dates and times while it is fresh",
    "Keep originals safe and hand over only copies until asked",
    "Treat any deadline printed on your own papers as real",
    "Speak to a qualified lawyer or a legal aid clinic about your specific facts",
]

_INSUFFICIENT_NEXT_STEP = (
    "Tell a little more — what was said or done, when it happened, "
    "and whether money, property, injury or a notice was involved — "
    "so this can be matched to a more specific next step."
)

_TIME_SENSITIVITY_URGENT = [
    "arrest", "arrested", "custody", "immediate danger", "right now",
    "threatening to kill", "violence", "injured badly", "hospital",
    "गिरफ्तार", "हिरासत", "मारने की धमकी", "अस्पताल",
]

_TIME_SENSITIVITY_DEADLINE = [
    "deadline", "last date", "due date", "expires", "expiry",
    "notice period", "must file", "within days", "by tomorrow",
    "today", "आखिरी तारीख", "समय सीमा",
]


def _quote(text: str) -> str:
    compact = re.sub(r"\s+", " ", (text or "")).strip()
    if len(compact) > MAX_QUOTE_CHARS:
        compact = compact[: MAX_QUOTE_CHARS - 1].rstrip() + "…"
    return compact


def _hits(text_lower: str, signals) -> int:
    score = 0
    for signal in signals:
        if signal in text_lower:
            # Longer, more specific signals say more than one word.
            score += max(1, len(signal.split()))
    return score


def detect_incident_category(text: str) -> tuple:
    """(category or None, [(category, score) ranked]).

    A tie between two well-matched categories is reported as ambiguity
    rather than silently resolved — guessing between two legal
    characters is exactly the thing this feature must not do.
    """
    text_lower = (text or "").lower()

    scored = []
    for category in _INCIDENT_CATEGORIES:
        score = _hits(text_lower, category["signals"])
        if score:
            scored.append((category, score))

    scored.sort(key=lambda item: item[1], reverse=True)

    if not scored or scored[0][1] < _MIN_CATEGORY_SCORE:
        return None, scored

    return scored[0][0], scored


def _time_sensitivity(text: str, mode: str, case_context=None) -> tuple:
    """(bool, note) — only from what was actually supplied."""
    text_lower = (text or "").lower()

    if mode == "case":
        hearing = _case_field(case_context, "next_hearing_date")
        if hearing:
            note = (
                f"The available case record lists a hearing on {hearing}. "
                "That date comes from the record, not from an estimate."
            )
            try:
                target = _date.fromisoformat(str(hearing)[:10])
                days = (target - _date.today()).days
                if 0 <= days <= 7:
                    return True, (
                        f"{note} It is {days} day(s) from now, so anything "
                        "due before that hearing should be done first."
                    )
            except ValueError:
                pass
            return False, note
        return False, (
            "The available case record does not list a next hearing date, "
            "so nothing here can be called time-sensitive."
        )

    if any(marker in text_lower for marker in _TIME_SENSITIVITY_URGENT):
        return True, (
            "You mentioned danger, arrest or injury. If anyone is in "
            "immediate danger, call 112; otherwise contact a lawyer "
            "without delay. This is based only on what you wrote."
        )

    if any(marker in text_lower for marker in _TIME_SENSITIVITY_DEADLINE):
        return True, (
            "You referred to a date or a deadline. Any date printed on "
            "your own papers should be treated as real and acted on "
            "promptly — this system has not verified it."
        )

    return False, (
        "Nothing you described states a deadline. If your papers carry "
        "a date, treat it as real."
    )


# ---------------------------------------------------------------------------
# CASE RECORD HELPERS
# ---------------------------------------------------------------------------

_CASE_ALIASES = {
    "cnr": ("cnr_number", "cnr"),
    "case_type": ("case_type",),
    "court": ("court_name",),
    "stage": ("current_case_stage", "stage", "status"),
    "next_hearing": ("next_hearing_date",),
    "filing_date": ("filing_date",),
    "judge": ("presiding_judge",),
    "petitioner": ("petitioner_name",),
    "advocate": ("petitioner_advocate", "handling_advocate"),
    "act": ("applied_act",),
    "section": ("applied_section",),
    "timeline": ("case_history_timeline", "timeline"),
    "orders": ("orders", "court_orders"),
    "documents": ("documents",),
}


def _case_field(context, key: str):
    """Read one logical field from a case snapshot, tolerating the two
    spellings the frontend and the fixture each use."""
    if not isinstance(context, dict):
        return None

    for alias in _CASE_ALIASES.get(key, (key,)):
        value = context.get(alias)
        if value not in (None, "", [], {}):
            return value
    return None


def _timeline_entries(context) -> list:
    raw = _case_field(context, "timeline")
    if not isinstance(raw, list):
        return []

    entries = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        entries.append(
            {
                "hearing_date": str(item.get("hearing_date") or "").strip(),
                "purpose": str(
                    item.get("purpose_of_hearing")
                    or item.get("purpose")
                    or ""
                ).strip(),
                "judge": str(
                    item.get("judge_title") or item.get("judge") or ""
                ).strip(),
            }
        )

    entries.sort(key=lambda entry: entry["hearing_date"] or "9999-99-99")
    return entries


# ---------------------------------------------------------------------------
# CONVERSATION STATE
# ---------------------------------------------------------------------------

_AFFIRMATIVES = {
    "yes", "yes.", "yeah", "yep", "yup", "y", "correct", "right",
    "haan", "ha", "han", "हाँ", "हां", "होय", "हो", "निश्चित",
}

_TEMPORAL_MARKERS = [
    "yesterday", "today", "this morning", "this evening", "last night",
    "last week", "two days", "three days", "a few days",
    "काल", "आज", "काला", "परवा", "गेल्या",
]


def is_affirmative(text: str) -> bool:
    return (text or "").strip().lower().strip(".!,") in _AFFIRMATIVES


def _is_temporal(text: str) -> bool:
    lowered = (text or "").lower()
    return any(marker in lowered for marker in _TEMPORAL_MARKERS)


def merge_context(text: str, history) -> str:
    """Fold earlier turns into what is analysed.

    Follow-ups like "it happened yesterday" or "yes" mean nothing on
    their own; they only make sense against what was said before. This
    is the whole of the memory system — the last few user turns, no
    embeddings, no summariser.
    """
    prior_user = [
        turn.get("text", "")
        for turn in history
        if turn.get("role") == "user" and turn.get("text")
    ]

    if not prior_user:
        return text

    short = len((text or "").split()) <= 8

    if not (is_affirmative(text) or _is_temporal(text) or short):
        return text

    joined = " ".join(prior_user[-3:] + [text or ""])
    return joined[:MAX_TEXT_CHARS]


def acknowledgement(text: str, history) -> str:
    if not history:
        return ""

    if is_affirmative(text):
        return "Understood — you said yes. "

    if _is_temporal(text) or len((text or "").split()) <= 8:
        quoted = _quote(text).rstrip(".!? ")
        return f"Noted: “{quoted}”. "

    return ""


class ConversationStore:
    """Session-level conversation state. One process, memory only.

    Deliberately small: the last handful of turns per conversation, no
    persistence, no summarising. Losing it on restart costs the user
    nothing but the first question again.
    """

    def __init__(self, max_turns: int = 12):
        self._turns: dict = {}
        self._lock = threading.Lock()
        self._max_turns = max_turns

    @staticmethod
    def new_id() -> str:
        return f"c_{uuid.uuid4().hex[:12]}"

    def known(self, conversation_id: str) -> bool:
        with self._lock:
            return conversation_id in self._turns

    def recent(self, conversation_id: str, limit: int = 6) -> list:
        with self._lock:
            turns = list(self._turns.get(conversation_id, []))
        return turns[-limit:]

    def append(self, conversation_id: str, role: str, text: str) -> None:
        with self._lock:
            turns = self._turns.setdefault(conversation_id, [])
            turns.append({"role": role, "text": text or ""})
            if len(turns) > self._max_turns:
                del turns[: len(turns) - self._max_turns]

    def last_follow_ups(self, conversation_id: str) -> list:
        """The questions the previous reply ended with — repeated after
        a short follow-up so the conversation reads like a conversation."""
        with self._lock:
            turns = list(self._turns.get(conversation_id, []))

        for turn in reversed(turns):
            if turn.get("role") == "assistant_followups":
                return list(turn.get("items") or [])
        return []

    def remember_follow_ups(self, conversation_id: str, items) -> None:
        with self._lock:
            turns = self._turns.setdefault(conversation_id, [])
            turns.append(
                {
                    "role": "assistant_followups",
                    "text": "",
                    "items": list(items or []),
                }
            )
            if len(turns) > self._max_turns:
                del turns[: len(turns) - self._max_turns]

    def clear(self, conversation_id: str) -> None:
        with self._lock:
            self._turns.pop(conversation_id, None)


CONVERSATIONS = ConversationStore()


# ---------------------------------------------------------------------------
# INCIDENT MODE
# ---------------------------------------------------------------------------


def analyse_incident(
    text: str,
    language: str = "en",
    guidance: dict | None = None,
    conversation_id: str = "",
    history=(),
    ack: str = "",
) -> dict:
    """Structured read of what somebody says happened to them."""
    raw = (text or "").strip()
    language = language if language in SUPPORTED_LANGUAGES else "en"

    category, ranked = detect_incident_category(raw)
    enough = len(raw) >= 25 and category is not None
    time_sensitive, time_note = _time_sensitivity(raw, "incident")

    warnings = []

    if not raw:
        warnings.append(
            "Nothing was written, so no incident could be read. "
            "Describe what happened, even in a sentence or two."
        )
    elif len(raw) > MAX_TEXT_CHARS:
        warnings.append(
            f"Only the first {MAX_TEXT_CHARS} characters were read."
        )
        raw = raw[:MAX_TEXT_CHARS]

    guidance = guidance or {"matched": False}

    if not raw:
        return {
            "mode": "incident",
            "language": language,
            "conversation_id": conversation_id,
            "acknowledgement": ack,
            "interpretation_source": SOURCE_PLACEHOLDER,
            "summary": "No description was provided.",
            "possible_issue": "",
            "explanation": (
                "Please describe what happened — what was said or done, "
                "when, and by whom. Nothing can be inferred from an "
                "empty description."
            ),
            "case_facts": [],
            "record_gaps": [],
            "next_steps": [],
            "preserve_information": [],
            "follow_up_questions": [
                "What happened, in your own words?",
                "When and where did it happen?",
            ],
            "warnings": warnings,
            "time_sensitive": False,
            "time_sensitivity_note": time_note,
            "matched_stage": None,
            "guidance": None,
            "legal_terms": [],
            "disclaimer": DISCLAIMER,
        }

    # ---- WHAT MAY HAVE HAPPENED -------------------------------------
    quote = _quote(raw)

    if category is not None:
        summary = (
            f"{category['label']}. "
            f"From what you wrote — “{quote}” — this reads like "
            f"{category['label'].lower().replace('possible ', '')}."
        )
        explanation = (
            f"In plain words: {category['label'].lower().replace('possible ', '')} "
            "is what your description resembles. That is a reading of "
            "your words, not a finding — nothing here has been "
            "verified, and the other side's version is not known."
        )
    else:
        summary = (
            f"Your description — “{quote}” — does not contain enough "
            "detail to place it in a category yet."
        )
        explanation = (
            "It may still be a legal matter, but deciding what kind "
            "would mean guessing, and guessing here is worse than "
            "saying so. Add a few facts and this will become specific."
        )
        warnings.append(
            "The description was too general to classify. No category "
            "has been asserted."
        )

    if len(ranked) >= 2 and ranked[0][1] == ranked[1][1]:
        first, second = ranked[0][0], ranked[1][0]
        warnings.append(
            f"Two readings fit equally well — {first['label'].lower()} "
            f"and {second['label'].lower()} — so the first is shown "
            "without being preferred."
        )

    # ---- POSSIBLE LEGAL ISSUE ---------------------------------------
    if category is not None:
        possible_issue = category["issue"]
    elif guidance.get("matched") and guidance.get("stage"):
        # The person wrote in court-stage language rather than as a
        # story, so the guidance set is what identifies it — and it
        # identifies a *stage*, never an offence.
        stage_name = guidance["stage"]
        possible_issue = (
            f"Based on what you described, this may indicate a matter "
            f"at the “{stage_name}” stage. That is how the wording "
            "matches the guidance set; it is not a finding about your "
            "case, and which legal provisions apply should be "
            "confirmed by a qualified lawyer."
        )
        summary = (
            f"Your description — “{quote}” — reads like the court "
            f"stage “{stage_name}”."
        )
        explanation = (
            "In plain words: that stage covers situations like this "
            + (
                f" — {guidance['why']} "
                if guidance.get("why")
                else ""
            )
            + "in general. It describes the stage, not your particular "
            "case, and nothing here has been verified."
        )
        warnings.append(
            f"It matched the guidance stage “{stage_name}” on the "
            "words used, not on any verified fact."
        )
    else:
        possible_issue = (
            "Based on what you described, something that may have a "
            "legal character appears to have happened, but the "
            "information given is insufficient to name the category. "
            "No section, offence or remedy has been assumed."
        )

    # ---- NEXT STEPS (existing guidance set first) --------------------
    next_steps = []

    if guidance.get("matched"):
        next_steps.append(guidance.get("what_to_do_next", ""))
        if guidance.get("stage"):
            warnings.append(
                f"This matched the guidance stage “{guidance['stage']}” "
                "on the words used, not on any verified fact."
            )
    elif not category and guidance.get("what_to_do_next"):
        # Nothing recognised at all: the guidance set's own honest
        # "no match" text is the correct thing to show. When a category
        # did match, its concrete steps say more than that boilerplate.
        next_steps.append(guidance["what_to_do_next"])

    next_steps.extend(
        (category["next_steps"] if category else [])
        or ([_INSUFFICIENT_NEXT_STEP] if not category else [])
    )

    if not next_steps:
        next_steps.append(_INSUFFICIENT_NEXT_STEP)

    next_steps.append(_GENERIC_NEXT_STEPS[-1])

    # ---- INFORMATION TO PRESERVE -------------------------------------
    preserve = list(
        (category["preserve"] if category else []) or _GENERIC_PRESERVE
    )

    # ---- WHAT ELSE WOULD HELP ----------------------------------------
    follow_ups = list(
        (category["follow_ups"] if category else [])
        or [
            "What exactly was said or done, and by whom?",
            "When and where did it happen?",
            "Was money, property, injury or a notice involved?",
        ]
    )

    # ---- LEGAL TERMS (existing glossary) -----------------------------
    legal_terms = glossary_terms_for(
        " ".join(
            part
            for part in [
                guidance.get("stage") or "",
                guidance.get("why") or "",
                possible_issue,
            ]
            if part
        )
    )

    # ---- MEMBER 2'S INTERPRETATION (the model seam) ------------------
    # Member 2's model, when connected, owns exactly the three reading
    # fields above. When it is not — today — the rule-based reading
    # stands and this says so in the response, so a placeholder is
    # never read as the final model output. Nothing below this seam is
    # model-owned: next steps, the preserve list, follow-ups, time
    # sensitivity, the glossary and the disclaimer stay platform
    # code, record or guidance driven either way.
    user_turns = [
        turn.get("text", "")
        for turn in (history or ())
        if isinstance(turn, dict)
        and turn.get("role") == "user"
        and turn.get("text")
    ]
    model = interpret(raw, language=language, history=user_turns)

    if model is not None:
        summary = model["summary"]
        possible_issue = model["possible_issue"]
        explanation = model["explanation"]
        interpretation_source = SOURCE_MODEL
    else:
        warnings.append(PLACEHOLDER_HEDGE)
        interpretation_source = SOURCE_PLACEHOLDER

    response = {
        "mode": "incident",
        "language": language,
        "conversation_id": conversation_id,
        "acknowledgement": ack,
        "interpretation_source": interpretation_source,
        "summary": summary,
        "possible_issue": possible_issue,
        "explanation": explanation,
        "case_facts": [],
        "record_gaps": [],
        "next_steps": next_steps,
        "preserve_information": preserve,
        "follow_up_questions": follow_ups,
        "warnings": warnings,
        "time_sensitive": time_sensitive,
        "time_sensitivity_note": time_note,
        "matched_stage": guidance.get("stage"),
        "guidance": guidance if guidance.get("matched") else None,
        "legal_terms": legal_terms,
        "disclaimer": DISCLAIMER,
    }
    if model is not None:
        # Carries which fields the model produced so handle_request can
        # hand them to translate_response as skip_fields — model text
        # is already in the user's language and is never re-translated.
        response[MODEL_FIELDS_KEY] = list(MODEL_FIELDS)
    return response


# ---------------------------------------------------------------------------
# CASE MODE
# ---------------------------------------------------------------------------

_CASE_INTENTS = (
    ("why_postponed", ["why", "postpon", "adjourn", "deferred", "reason for"]),
    ("next_hearing", [
        "next hearing", "next date", "when is", "when will",
        "hearing date", "court date", "when is my", "date of hearing",
    ]),
    ("last_hearing", [
        "last hearing", "previous hearing", "last date",
        "what happened in", "earlier hearing", "past hearing",
    ]),
    ("order", [
        "order", "judgment", "judgement", "what did the court say",
        "written direction", "the court directed",
    ]),
    ("documents", [
        "document", "papers to", "file the", "submit", "evidence to",
        "what do i need to", "what should i file",
    ]),
    ("next_steps", [
        "what should i do", "next step", "what to do", "advice",
        "guide me", "what happens now", "what am i supposed",
    ]),
    ("status", [
        "status", "current stage", "stage", "progress",
        "what is happening", "where is my case", "how is my case",
    ]),
    ("parties", [
        "who is the judge", "who are the parties", "petitioner",
        "respondent", "who filed", "advocate",
    ]),
)


def detect_case_intent(text: str) -> str:
    lowered = (text or "").lower()
    for intent, markers in _CASE_INTENTS:
        if any(marker in lowered for marker in markers):
            return intent
    return "overview"


def default_case_guidance(stage):
    """Existing guidance for a case stage, exact match first.

    `get_next_steps` wants the phrasing the guidance set itself uses;
    the record usually says something shorter ("Arguments"), so the
    scorer in guidance_match gets a second try. Nothing is invented
    when neither matches — the caller says so instead.
    """
    if not isinstance(stage, str) or not stage.strip():
        return None

    exact = get_next_steps(stage)
    if exact.get("matched"):
        return exact

    scored = match_guidance(stage)
    if scored.get("matched"):
        return scored

    return None


def _guidance_action(guide) -> str:
    if not isinstance(guide, dict):
        return ""
    return guide.get("suggested_action") or guide.get("what_to_do_next") or ""


def _guidance_stage_name(guide) -> str | None:
    if not isinstance(guide, dict):
        return None
    return guide.get("case_stage") or guide.get("stage")


def answer_case_question(
    text: str,
    case_context: dict | None = None,
    language: str = "en",
    case_guidance: dict | None = None,
    conversation_id: str = "",
    history=(),
    ack: str = "",
) -> dict:
    """Answer a question about a case using only the record supplied.

    `case_context` is the frontend's snapshot of one Case record. It is
    never extended, inferred from, or second-guessed here.
    """
    raw = (text or "").strip()
    language = language if language in SUPPORTED_LANGUAGES else "en"

    intent = detect_case_intent(raw)
    warnings = []
    record_gaps: list = []
    facts: list = []

    has_context = isinstance(case_context, dict) and bool(case_context)

    stage = _case_field(case_context, "stage")
    cnr = _case_field(case_context, "cnr")
    next_hearing = _case_field(case_context, "next_hearing")
    court = _case_field(case_context, "court")
    case_type = _case_field(case_context, "case_type")
    judge = _case_field(case_context, "judge")
    timeline = _timeline_entries(case_context)

    if not has_context:
        warnings.append(
            "No case record was shared with this question, so nothing "
            "about any particular case has been stated."
        )
    else:
        if cnr:
            facts.append(f"CNR: {cnr}")
        if case_type:
            facts.append(f"Case type: {case_type}")
        if court:
            facts.append(f"Court: {court}")
        if stage:
            facts.append(f"Current stage: {stage}")
        if next_hearing:
            facts.append(f"Next hearing: {next_hearing}")
        if judge:
            facts.append(f"Presiding judge: {judge}")

    dated = [entry for entry in timeline if entry["hearing_date"]]
    past = [
        entry
        for entry in dated
        if entry["hearing_date"] < _date.today().isoformat()
    ]
    upcoming = [
        entry
        for entry in dated
        if entry["hearing_date"] >= _date.today().isoformat()
    ]
    last_past = past[-1] if past else None
    next_listed = upcoming[0] if upcoming else None

    # ---- THE ANSWER ---------------------------------------------------
    if not has_context:
        answer = (
            "No case information came with your question, so I can "
            "only speak generally. Select your case (or send its CNR) "
            "and I will answer from that record alone."
        )
        record_gaps.append("No case record was supplied with the question.")
    elif intent == "status":
        answer = (
            f"The available case record shows this matter at the "
            f"“{stage}” stage"
            + (
                f", with the next hearing listed on {next_hearing}."
                if next_hearing
                else ". It does not list a next hearing date."
            )
        )
        if not stage:
            answer = (
                "The available case record does not state a current "
                "stage for this matter."
            )
            record_gaps.append("No current stage in the record.")
    elif intent == "last_hearing":
        if last_past:
            answer = (
                f"The last hearing shown in the record is "
                f"{last_past['hearing_date']}"
                + (
                    f", listed for “{last_past['purpose']}”"
                    if last_past["purpose"]
                    else ""
                )
                + "."
            )
        elif next_listed:
            answer = (
                "The record contains no hearing that has already "
                f"passed. Its earliest listed entry is "
                f"{next_listed['hearing_date']}"
                + (
                    f", for “{next_listed['purpose']}”"
                    if next_listed["purpose"]
                    else ""
                )
                + "."
            )
            record_gaps.append(
                "The record does not describe what happened at any "
                "past hearing."
            )
        else:
            answer = (
                "The available case record does not contain any "
                "hearing entries, so nothing about a past hearing can "
                "be stated."
            )
            record_gaps.append("No hearing entries in the record.")
    elif intent == "next_hearing":
        if next_hearing:
            answer = f"The record lists the next hearing as {next_hearing}."
            if next_listed and next_listed["hearing_date"] == str(next_hearing):
                if next_listed["purpose"]:
                    answer += f" The listed purpose is “{next_listed['purpose']}”."
                if next_listed["judge"]:
                    answer += f" Before {next_listed['judge']}."
        else:
            answer = (
                "The available case record does not list a next "
                "hearing date. Nothing has been guessed in its place."
            )
            record_gaps.append("No next hearing date in the record.")
    elif intent == "order":
        orders = _case_field(case_context, "orders")
        if isinstance(orders, list) and orders:
            answer = (
                "The record carries "
                f"{len(orders)} order entr{'y' if len(orders) == 1 else 'ies'}. "
                "The most recent is quoted in the Court Orders screen."
            )
        else:
            answer = (
                "The available case record does not include any court "
                "order, so nothing about what an order said can be "
                "stated here. Orders appear on the Court Orders screen "
                "once they are on file."
            )
            record_gaps.append("No orders in the supplied record.")
    elif intent == "why_postponed":
        evidence = None
        if last_past:
            evidence = last_past
        elif next_listed:
            evidence = next_listed

        if evidence:
            answer = (
                "The available court record shows the matter listed "
                f"on {evidence['hearing_date']}"
                + (
                    f" for “{evidence['purpose']}”"
                    if evidence["purpose"]
                    else ""
                )
                + ", but it does not state the reason for any "
                "postponement. No reason has been inferred."
            )
            record_gaps.append(
                "The record does not state why a hearing was "
                "adjourned or postponed."
            )
        else:
            answer = (
                "The available case record contains no hearing entry "
                "to explain, and it does not state a reason for any "
                "postponement."
            )
            record_gaps.append("No hearing entry explains a postponement.")
    elif intent == "documents":
        answer = (
            "The record does not list documents to be filed, so I "
            "will not name any. In general, the next step for this "
            "stage is set out below — confirm the exact papers with "
            "your advocate or the notice you were served."
        )
        record_gaps.append(
            "No document requirement is stated in the supplied record."
        )
    elif intent == "next_steps":
        answer = (
            "Based on the stage recorded for this matter, the "
            "guidance below applies. It is general guidance for that "
            "stage, not advice on your particular facts."
        )
    elif intent == "parties":
        petitioner = _case_field(case_context, "petitioner")
        respondents = case_context.get("respondents_list") if has_context else None
        pieces = []
        if petitioner:
            pieces.append(f"petitioner {petitioner}")
        if isinstance(respondents, list) and respondents:
            pieces.append("respondents " + ", ".join(str(r) for r in respondents))
        answer = (
            "As recorded: "
            + (" and ".join(pieces) if pieces else "parties are not listed")
            + (f", before {judge}." if judge else ".")
        )
        if not pieces:
            record_gaps.append("The record does not name the parties.")
    else:  # overview
        if stage or next_hearing:
            answer = (
                "This matter is recorded as "
                + (f"a {case_type}" if case_type else "a case")
                + (f" in {court}" if court else "")
                + (f", currently at the “{stage}” stage" if stage else "")
                + (
                    f", with the next hearing on {next_hearing}."
                    if next_hearing
                    else ", and the record lists no next hearing date."
                )
            )
        else:
            answer = (
                "The supplied record carries too little to summarise: "
                "no stage and no next hearing date are on it."
            )
            record_gaps.append("The record has no stage and no hearing date.")

    # ---- NEXT STEPS from the existing guidance set --------------------
    next_steps = []
    guided_stage = _guidance_stage_name(case_guidance)
    if case_guidance and case_guidance.get("matched") and guided_stage:
        action = _guidance_action(case_guidance)
        if action:
            next_steps.append(action)
        facts.append(f"Guidance stage matched: {guided_stage}")
    elif stage:
        warnings.append(
            "The current stage did not match any entry in the "
            "guidance set, so no stage-specific next step has been "
            "invented."
        )

    next_steps.extend(
        [
            "Read the latest notice or order yourself alongside this answer",
            "Confirm anything action-changing with your advocate before acting",
        ]
    )

    # ---- FOLLOW-UPS ----------------------------------------------------
    follow_ups = []
    if intent != "next_hearing":
        follow_ups.append("When is my next hearing?")
    if intent != "last_hearing":
        follow_ups.append("What happened in my last hearing?")
    if intent != "order":
        follow_ups.append("What did the latest order say?")
    follow_ups.append("What should I do next?")

    time_sensitive, time_note = _time_sensitivity(raw, "case", case_context)

    if not raw:
        warnings.append("No question was written, so nothing was answered.")
        answer = "Ask a question about the case — for example, when the next hearing is."

    legal_terms = glossary_terms_for(
        " ".join(part for part in [stage or "", answer] if part)
    )

    return {
        "mode": "case",
        "language": language,
        "conversation_id": conversation_id,
        "acknowledgement": ack,
        "summary": _quote(answer),
        "possible_issue": "",
        "explanation": answer,
        "case_facts": facts,
        "record_gaps": record_gaps,
        "next_steps": next_steps,
        "preserve_information": [],
        "follow_up_questions": follow_ups,
        "warnings": warnings,
        "time_sensitive": time_sensitive,
        "time_sensitivity_note": time_note,
        "matched_stage": (
            _guidance_stage_name(case_guidance)
            if case_guidance and case_guidance.get("matched")
            else (stage if isinstance(stage, str) else None)
        ),
        "guidance": case_guidance if case_guidance else None,
        "legal_terms": legal_terms,
        "disclaimer": DISCLAIMER,
    }


# ---------------------------------------------------------------------------
# TRANSLATION OF A WHOLE RESPONSE
# ---------------------------------------------------------------------------

_TRANSLATABLE_STRINGS = (
    "acknowledgement",
    "summary",
    "possible_issue",
    "explanation",
    "time_sensitivity_note",
    "disclaimer",
)

_TRANSLATABLE_LISTS = (
    "case_facts",
    "record_gaps",
    "next_steps",
    "preserve_information",
    "follow_up_questions",
    "warnings",
)


def translate_response(
    payload: dict, translator, protected_values=(), *, skip_fields=(),
) -> dict:
    """Return a copy with every prose field in the requested language.

    `translator(text, language) -> str`. A field whose facts cannot be
    preserved stays in English and a warning says so; one broken field
    never discards an otherwise good answer.

    `skip_fields` are already written in the requested language (they
    came from Member 2's interpretation model) and pass through
    verbatim — re-translating them would only corrupt them.
    """
    language = payload.get("language", "en")

    if language == "en" or translator is None:
        return payload

    extra = [str(value) for value in protected_values if value]
    failed = []

    def one(value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            return value
        try:
            spans = extract_protected_spans(value)
            for index, item in enumerate(extra):
                if item and item in value and item not in spans:
                    spans.append(item)
            if not spans:
                return translator(value, language)
            restored, missing = unmask_protected_spans(
                translator(mask_protected_spans(value, spans), language),
                spans,
            )
            if missing:
                raise FactPreservationError(missing)
            return restored
        except FactPreservationError:
            failed.append(value)
            return value
        except Exception:
            failed.append(value)
            return value

    out = dict(payload)

    for field in _TRANSLATABLE_STRINGS:
        if field in skip_fields:
            continue
        value = out.get(field)
        if isinstance(value, str) and value.strip():
            out[field] = one(value)

    for field in _TRANSLATABLE_LISTS:
        value = out.get(field)
        if isinstance(value, list):
            out[field] = [one(item) if isinstance(item, str) else item for item in value]

    guidance = out.get("guidance")
    if isinstance(guidance, dict):
        new_guidance = dict(guidance)
        for field in ("what_to_do_next", "why"):
            if isinstance(new_guidance.get(field), str):
                new_guidance[field] = one(new_guidance[field])
        out["guidance"] = new_guidance

    terms = out.get("legal_terms")
    if isinstance(terms, list):
        lang_key = f"plain_{language}"
        new_terms = []
        for term in terms:
            if not isinstance(term, dict):
                continue
            item = dict(term)
            localised = term.get(lang_key)
            if isinstance(localised, str) and localised.strip():
                item["plain"] = localised
            elif isinstance(term.get("plain"), str):
                item["plain"] = one(term["plain"])
            new_terms.append(item)
        out["legal_terms"] = new_terms

    if failed:
        warnings = list(out.get("warnings") or [])
        warnings.append(
            f"Some text could not be translated into this language "
            f"without risking a change to names, dates or numbers "
            f"({len(failed)} part(s)), so it is left in English."
        )
        out["warnings"] = warnings

    return out


# ---------------------------------------------------------------------------
# ORCHESTRATION — the body of POST /api/what-happened
# ---------------------------------------------------------------------------


class WhatHappenedError(ValueError):
    """A request problem the caller can safely show to the user."""


def handle_request(
    payload: dict,
    *,
    translator=None,
    guidance_fn=None,
    case_guidance_fn=None,
    store: ConversationStore | None = None,
) -> dict:
    """Validate, answer, remember. Everything model-facing is injected.

    guidance_fn(text) -> the /api/guidance body
    case_guidance_fn(stage) -> the next_steps_guidance_lookup body
    translator(text, language) -> text in `language`
    """
    payload = payload or {}

    mode = payload.get("mode")
    if mode not in SUPPORTED_MODES:
        raise WhatHappenedError(
            "mode must be 'incident' or 'case'."
        )

    language = payload.get("language") or "en"
    if language not in SUPPORTED_LANGUAGES:
        raise WhatHappenedError(
            "language must be one of: en, hi, mr."
        )

    text = payload.get("text")
    if text is None:
        text = ""
    if not isinstance(text, str):
        raise WhatHappenedError("text must be a string.")
    if len(text) > 20000:
        raise WhatHappenedError("text is too long.")

    case_context = payload.get("case_context")
    if case_context is not None and not isinstance(case_context, dict):
        raise WhatHappenedError("case_context must be an object.")

    store = store or CONVERSATIONS
    conversation_id = payload.get("conversation_id") or ""
    if not store.known(conversation_id):
        conversation_id = ConversationStore.new_id()

    history = store.recent(conversation_id)
    ack = acknowledgement(text, history)
    analysis_text = merge_context(text, history)

    store.append(conversation_id, "user", text)

    if mode == "incident":
        guidance_fn = guidance_fn or match_guidance
        guidance = (
            guidance_fn(analysis_text)
            if analysis_text.strip()
            else {"matched": False}
        )
        response = analyse_incident(
            analysis_text,
            language=language,
            guidance=guidance,
            conversation_id=conversation_id,
            history=history,
            ack=ack,
        )
        response["user_text"] = text
        protected_values = []
        # The model's own fields (if Member 2's model was used) are
        # already in the user's language — never translated again.
        skip_fields = response.pop(MODEL_FIELDS_KEY, [])
    else:
        case_guidance_fn = case_guidance_fn or default_case_guidance
        stage = _case_field(case_context, "stage")
        case_result = (
            case_guidance_fn(stage)
            if isinstance(stage, str) and stage.strip()
            else None
        )
        response = answer_case_question(
            analysis_text,
            case_context=case_context,
            language=language,
            case_guidance=case_result,
            conversation_id=conversation_id,
            history=history,
            ack=ack,
        )
        response["user_text"] = text
        # Case answers are read off the record — no interpretation
        # model is ever involved in this mode.
        response["interpretation_source"] = SOURCE_RECORD
        protected_values = _protected_values_from_case(case_context)
        skip_fields = []

    # Repeated questions after a short reply keep the old follow-ups
    # alive, which is what makes "yes" land on something specific.
    if history and len((text or "").split()) <= 8 and not response["acknowledgement"]:
        previous = store.last_follow_ups(conversation_id)
        if previous:
            response["follow_up_questions"] = previous + [
                item
                for item in response.get("follow_up_questions", [])
                if item not in previous
            ]

    follow_ups = response.get("follow_up_questions") or []
    store.remember_follow_ups(conversation_id, follow_ups)
    store.append(
        conversation_id,
        "assistant",
        response.get("summary") or response.get("explanation") or "",
    )

    response = translate_response(
        response, translator, protected_values, skip_fields=skip_fields,
    )
    response["language"] = language
    response["conversation_id"] = conversation_id
    response["mode"] = mode
    return response


def _protected_values_from_case(case_context) -> list:
    """Everything on the record a translation must reproduce exactly."""
    if not isinstance(case_context, dict):
        return []

    values = []

    def add(value):
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
        elif isinstance(value, list):
            for item in value:
                add(item)

    for key in (
        "cnr_number",
        "cnr",
        "filing_number",
        "registration_number",
        "next_hearing_date",
        "filing_date",
        "registration_date",
        "first_hearing_date",
        "applied_section",
        "applied_act",
        "petitioner_name",
        "petitioner_advocate",
        "presiding_judge",
        "court_name",
        "current_case_stage",
    ):
        add(case_context.get(key))

    for entry in _timeline_entries(case_context):
        add(entry["hearing_date"])

    return values

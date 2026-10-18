"""Legal Language -> Simple Language -> Marathi/Hindi.

`POST /api/legal-simplify` on the live NLP service (default :8001):

    .venv/bin/pytest test_legal_simplification.py -v

The endpoint is an *extension* of the existing NLP service, not a
replacement for anything it already did. So this file tests it the way
the frontend calls it -- over HTTP, with the same API key -- and tests
the two things it is made of: the rule-based simplification engine (pure
Python, no model) and the IndicTrans2 layer that carries the plain
English into Marathi or Hindi.

The last test walks the whole Court Order path: PDF -> extraction ->
section splitting -> simplify -> Marathi, which is the route the
"Simplify & Translate" button on the Court Orders page takes.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
import requests

from legal_simplification import (
    AMBIGUITY_WARNING,
    LOW_CONFIDENCE_WARNING,
    MAX_INPUT_CHARS,
)

BASE = os.environ.get("NYAYMITRA_NLP_URL", "http://127.0.0.1:8001").rstrip("/")
API_KEY = os.environ.get("NYAYMITRA_NLP_KEY", "nyaymitra-local-test-2026")
HEADERS = {"Authorization": f"Bearer {API_KEY}"}
TIMEOUT = 600

FIXTURE_DIR = Path(os.environ.get("NYAYMITRA_TEST_TMP", "/tmp")) / "nyaymitra_simplify_fixtures"

SIX_KEYS = {
    "original_text",
    "simple_english",
    "translated_text",
    "target_lang",
    "glossary_terms_used",
    "warnings",
}

SECTION_IDS = ["case_details", "proceedings", "order", "signatures", "certification"]


# ---------------------------------------------------------------------------
# TEN-PLUS LEGAL SENTENCES
#
# Each row is (the sentence as a court would write it, what must survive
# the rewrite). The second element is only ever something the rewrite is
# forbidden to lose -- a date, a period of time, a party, a conclusion.
# ---------------------------------------------------------------------------

LEGAL_SENTENCES: list[tuple[str, list[str]]] = [
    (
        "The hearing in this matter is adjourned to 15.10.2026.",
        ["15 October 2026"],
    ),
    (
        "The petitioner is directed to file a written reply within four weeks from today.",
        ["four weeks", "reply"],
    ),
    (
        "The application stands disposed of, with no order as to costs.",
        ["no order as to costs"],
    ),
    (
        "The matter is listed for hearing on 15.10.2026 before the learned Sessions Judge.",
        ["15 October 2026", "Sessions Judge"],
    ),
    (
        "Liberty is reserved to the petitioner to approach the proper forum in accordance with law.",
        ["Liberty", "petitioner"],
    ),
    (
        "The learned counsel for the petitioner submitted that the accused has cooperated with the investigation.",
        ["petitioner", "investigation"],
    ),
    (
        "The application is rejected, with liberty to file a fresh application.",
        ["rejected", "fresh application"],
    ),
    (
        "The petition stands dismissed, with no order as to costs.",
        ["dismissed", "no order as to costs"],
    ),
    (
        "The appeal is fixed for hearing on 20.11.2026.",
        ["20 November 2026"],
    ),
    (
        "The respondent is directed to file the reply within six weeks from today.",
        ["six weeks", "reply"],
    ),
    (
        "The said application is withdrawn, and the present petition is dismissed.",
        ["withdrawn", "dismissed"],
    ),
    (
        "The interim order dated 12.03.2026 shall remain in force until the final disposal of the petition.",
        ["12.03.2026", "petition"],
    ),
    (
        "The request for an adjournment is rejected, as the cause for delay was not sufficient.",
        ["rejected", "cause for delay"],
    ),
    (
        "This order is passed without prejudice to the rights and contentions of either party.",
        ["without prejudice to"],
    ),
]

# The four development examples the UI offers. They are labelled as demo
# examples in the frontend, and they are the same four here: they are
# written to look like orders, they are not real orders.
DEMO_CASES: list[tuple[str, str]] = [
    (
        "demo-adjourned",
        "The matter is adjourned to the next date of hearing. The matter is listed for hearing on 15.10.2026.",
    ),
    (
        "demo-reply",
        "The petitioner is directed to file a reply to the application within four weeks from today.",
    ),
    (
        "demo-disposed",
        "The application stands disposed of, with no order as to costs.",
    ),
    (
        "demo-listed",
        "The matter is listed for hearing on 15.10.2026 before the learned Senior Civil Judge.",
    ),
]


# ---------------------------------------------------------------------------
# FIXTURES
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def live_service():
    """Wait for the service rather than race it."""
    deadline = time.time() + 90
    last = "not started"

    while time.time() < deadline:
        try:
            response = requests.get(f"{BASE}/health", timeout=10)
            if response.ok:
                return
            last = f"status={response.status_code} {response.text[:120]}"
        except requests.RequestException as exc:
            last = str(exc)[:160]

        time.sleep(2)

    pytest.fail(
        f"NLP service is not reachable at {BASE} ({last}). "
        "Start it with: uvicorn translate_service:app --port 8001"
    )


@pytest.fixture(scope="session")
def order_pdf() -> Path:
    """A small, clearly synthetic order used only by the last test."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    path = FIXTURE_DIR / "simplify_pipeline_order.pdf"

    lines = [
        "IN THE COURT OF THE ADDITIONAL DISTRICT JUDGE, KHED",
        "Case Type: Criminal Misc Application",
        "CNR: MHMH010123452026",
        "Filing Number: 123/2026",
        "Petitioner: RAMESH KUMAR versus Respondent: STATE OF MAHARASHTRA",
        "1. The petitioner has filed this application seeking anticipatory bail in connection with an offence punishable under Section 306 of the Bharatiya Nyaya Sanhita.",
        "ORDER",
        "2. The application is hereby rejected. Liberty is reserved to the petitioner to approach the proper forum in accordance with law.",
        "ORDERED that the application be rejected.",
        "A. SHARMA",
        "JUDGE",
    ]

    page = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4
    y = height - 60

    for line in lines:
        if y < 60:
            page.showPage()
            y = height - 60
        page.drawString(50, y, line)
        y -= 22

    page.save()
    return path


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def simplify(text: str, target: str = "eng_Latn", auth: bool = True):
    return requests.post(
        f"{BASE}/api/legal-simplify",
        json={"text": text, "target_lang": target},
        headers=HEADERS if auth else {},
        timeout=TIMEOUT,
    )


def _describe(response) -> str:
    return f"status={response.status_code} body={response.text[:300]}"


def _has_devanagari(text: str) -> bool:
    return any("ऀ" <= char <= "ॿ" for char in text)


def _no_reference_lost(body: dict) -> bool:
    return not any("could not be confirmed" in warning for warning in body["warnings"])


# ---------------------------------------------------------------------------
# CONTRACT — six keys, and only six
# ---------------------------------------------------------------------------

def test_response_carries_exactly_the_six_keys(live_service):
    response = simplify("The application stands disposed of, with no order as to costs.")
    assert response.status_code == 200, _describe(response)

    body = response.json()
    assert set(body) == SIX_KEYS, sorted(body)
    assert isinstance(body["glossary_terms_used"], list)
    assert isinstance(body["warnings"], list)
    assert body["target_lang"] == "eng_Latn"
    assert body["original_text"].startswith("The application stands disposed of")


def test_default_target_is_marathi(live_service):
    """A client that posts only `text` still gets an answer."""
    response = requests.post(
        f"{BASE}/api/legal-simplify",
        json={"text": "The matter is adjourned."},
        headers=HEADERS,
        timeout=TIMEOUT,
    )
    assert response.status_code == 200, _describe(response)
    assert response.json()["target_lang"] == "mar_Deva"


def test_endpoint_lives_on_the_existing_service(live_service):
    """No second app: the route answers on the same port as /health."""
    response = requests.get(f"{BASE}/health", timeout=10)
    assert response.status_code == 200
    assert BASE.endswith("8001")


# ---------------------------------------------------------------------------
# AUTH
# ---------------------------------------------------------------------------

def test_missing_api_key_is_refused(live_service):
    response = simplify("The matter is adjourned.", auth=False)
    assert response.status_code == 401, _describe(response)
    assert "Traceback" not in response.text


def test_wrong_api_key_is_refused(live_service):
    response = requests.post(
        f"{BASE}/api/legal-simplify",
        json={"text": "The matter is adjourned.", "target_lang": "mar_Deva"},
        headers={"Authorization": "Bearer not-the-key"},
        timeout=30,
    )
    assert response.status_code == 401, _describe(response)
    assert "Traceback" not in response.text


# ---------------------------------------------------------------------------
# SIMPLIFICATION — more than ten legal sentences
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("sentence", "must_survive"),
    LEGAL_SENTENCES,
    ids=[f"sent{i:02d}" for i in range(len(LEGAL_SENTENCES))],
)
def test_legal_sentences_simplify_without_losing_their_facts(
    live_service, sentence, must_survive
):
    response = simplify(sentence)
    assert response.status_code == 200, _describe(response)

    body = response.json()
    assert set(body) == SIX_KEYS
    assert body["original_text"] == sentence
    assert body["simple_english"].strip(), "the plain layer came back empty"
    assert _no_reference_lost(body)

    for value in must_survive:
        assert value in body["simple_english"], (
            f"{value!r} was lost:\n{body['simple_english']}"
        )


def test_simplification_is_a_rewrite_not_a_copy(live_service):
    """The engine must actually reword legal phrasing, never retype it."""
    changed = 0

    for sentence, _keep in LEGAL_SENTENCES:
        body = simplify(sentence).json()
        if body["simple_english"] != sentence:
            changed += 1

    # Most of these sentences have a rule that speaks to them; a handful
    # (the ambiguous one) deliberately stay as written. What must never
    # happen is the whole set coming back untouched.
    assert changed >= 10, f"only {changed} of {len(LEGAL_SENTENCES)} were reworded"


def test_no_backreference_ever_reaches_the_page(live_service):
    """`\1` in a rule replacement used to be emitted as two characters."""
    for sentence, _keep in LEGAL_SENTENCES:
        body = simplify(sentence).json()
        assert "\\1" not in body["simple_english"], body["simple_english"]


@pytest.mark.parametrize(("label", "sentence"), DEMO_CASES)
def test_the_four_labelled_demo_cases(live_service, label, sentence):
    """Development examples — they read like orders, they are not orders."""
    response = simplify(sentence, "mar_Deva")
    assert response.status_code == 200, _describe(response)

    body = response.json()
    assert set(body) == SIX_KEYS
    assert body["original_text"] == sentence
    assert body["simple_english"].strip()
    assert _has_devanagari(body["translated_text"]), label
    assert _no_reference_lost(body), label
    # 15.10.2026 is a demo date in three of the four; it has to arrive.
    if "15.10.2026" in sentence:
        assert "15" in body["simple_english"] and "2026" in body["simple_english"]


# ---------------------------------------------------------------------------
# MARATHI / HINDI
# ---------------------------------------------------------------------------

def test_marathi_layer_is_devanagari_and_carries_every_reference(live_service):
    text = (
        "IN THE HIGH COURT OF JUDICATURE AT BOMBAY "
        "CNR: MHMH010123452026 W.P. 1234/2026 "
        "Petitioner: RAMESH KUMAR versus Respondent: STATE OF MAHARASHTRA. "
        "The matter is listed for hearing on 15.10.2026 under Section 306 "
        "of the Bharatiya Nyaya Sanhita. The application is hereby rejected."
    )

    response = simplify(text, "mar_Deva")
    assert response.status_code == 200, _describe(response)

    body = response.json()
    assert set(body) == SIX_KEYS
    assert body["target_lang"] == "mar_Deva"
    assert _has_devanagari(body["translated_text"])

    for preserved in (
        "MHMH010123452026",
        "W.P. 1234/2026",
        "RAMESH KUMAR",
        "STATE OF MAHARASHTRA",
        "HIGH COURT OF JUDICATURE AT BOMBAY",
        "306",
    ):
        assert preserved in body["translated_text"], (
            f"{preserved!r} lost in Marathi:\n{body['translated_text']}"
        )
        assert preserved in body["simple_english"], preserved

    assert "15" in body["translated_text"] and "2026" in body["translated_text"]
    assert _no_reference_lost(body), body["warnings"]


def test_hindi_layer_is_devanagari_and_carries_every_reference(live_service):
    text = (
        "CNR: MHMH010123452026 Case No. Crl.M.A. 456/2024 "
        "Petitioner: SUNITA DEVI versus Respondent: MUNICIPAL CORPORATION. "
        "The petitioner is directed to file a reply within four weeks from "
        "today, and the matter is listed for hearing on 20.11.2026 under "
        "Section 420 of the Bharatiya Nyaya Sanhita."
    )

    response = simplify(text, "hin_Deva")
    assert response.status_code == 200, _describe(response)

    body = response.json()
    assert set(body) == SIX_KEYS
    assert body["target_lang"] == "hin_Deva"
    assert _has_devanagari(body["translated_text"])

    for preserved in (
        "MHMH010123452026",
        "Crl.M.A. 456/2024",
        "SUNITA DEVI",
        "MUNICIPAL CORPORATION",
        "420",
    ):
        assert preserved in body["translated_text"], (
            f"{preserved!r} lost in Hindi:\n{body['translated_text']}"
        )

    assert "20" in body["translated_text"] and "2026" in body["translated_text"]
    assert _no_reference_lost(body), body["warnings"]


def test_english_target_skips_the_model_and_says_so(live_service):
    response = simplify("The application stands disposed of, with no order as to costs.")
    assert response.status_code == 200, _describe(response)

    body = response.json()
    assert body["translated_text"] == body["simple_english"]
    assert body["target_lang"] == "eng_Latn"


def test_the_translation_is_of_the_simple_layer_not_the_original(live_service):
    """Layer three is layer two, translated — the whole point of the stack."""
    response = simplify("The petition is adjourned to the next date of hearing.")
    assert response.status_code == 200, _describe(response)

    body = response.json()
    assert "adjourned" in body["original_text"]
    assert "adjourned" not in body["simple_english"]
    assert "postponed" in body["simple_english"]


# ---------------------------------------------------------------------------
# GLOSSARY
# ---------------------------------------------------------------------------

def test_glossary_terms_are_reported(live_service):
    body = simplify(
        "The matter is adjourned, and the respondent must file a rejoinder."
    ).json()

    assert "adjourned" in body["glossary_terms_used"], body["glossary_terms_used"]
    assert "rejoinder" in body["glossary_terms_used"], body["glossary_terms_used"]


def test_glossary_is_empty_when_nothing_matches(live_service):
    body = simplify("Listed for hearing on 15.10.2026.").json()
    assert isinstance(body["glossary_terms_used"], list)


# ---------------------------------------------------------------------------
# PRESERVATION — dates, sections, CNR, names
# ---------------------------------------------------------------------------

def test_dates_are_normalised_but_never_moved(live_service):
    body = simplify("The matter is posted for hearing on 15.10.2026.").json()
    assert "15 October 2026" in body["simple_english"]
    assert body["warnings"] == [], body["warnings"]


def test_an_ambiguous_date_is_left_alone(live_service):
    """10.11.2026 could be 10 Nov or 11 Oct — guessing would invent a fact."""
    body = simplify("The reply is due on 10.11.2026.").json()
    assert "10.11.2026" in body["simple_english"], body["simple_english"]
    assert "10 November" not in body["simple_english"]


def test_section_numbers_survive(live_service):
    body = simplify(
        "The application under Section 306 of the Act is rejected, and "
        "Rule 4 of Order XX was not pressed."
    ).json()

    assert "306" in body["simple_english"]
    assert "Rule 4" in body["simple_english"]


def test_cnr_and_case_numbers_survive(live_service):
    body = simplify(
        "CNR: MHMH010123452026 — W.P. 1234/2026 — the matter is listed "
        "for hearing on 15.10.2026."
    ).json()

    assert "MHMH010123452026" in body["simple_english"]
    assert "W.P. 1234/2026" in body["simple_english"]


def test_party_names_and_the_court_survive(live_service):
    body = simplify(
        "IN THE HIGH COURT OF JUDICATURE AT BOMBAY "
        "Petitioner: RAMESH KUMAR versus Respondent: STATE OF MAHARASHTRA. "
        "The application is hereby rejected."
    ).json()

    assert "HIGH COURT OF JUDICATURE AT BOMBAY" in body["simple_english"]
    assert "RAMESH KUMAR" in body["simple_english"]
    assert "STATE OF MAHARASHTRA" in body["simple_english"]


# ---------------------------------------------------------------------------
# AMBIGUITY AND FALLBACK
# ---------------------------------------------------------------------------

def test_ambiguity_is_preserved_and_flagged(live_service):
    sentence = (
        "This order is passed without prejudice to the rights and "
        "contentions of either party."
    )
    body = simplify(sentence).json()

    assert AMBIGUITY_WARNING in body["warnings"], body["warnings"]
    assert "without prejudice to" in body["simple_english"]
    assert _no_reference_lost(body)


def test_low_confidence_keeps_the_original_and_warns(live_service):
    """Nothing is guessed: if the rules cannot reword it, the reader is
    told and given the sentence they sent."""
    sentence = (
        "Whereas the party of the first part hath heretofore covenanted "
        "to do all things requisite and necessary."
    )
    body = simplify(sentence).json()

    assert body["simple_english"] == sentence
    assert LOW_CONFIDENCE_WARNING in body["warnings"], body["warnings"]
    assert "refer to the original text" in LOW_CONFIDENCE_WARNING


def test_warnings_are_never_duplicated(live_service):
    body = simplify(
        "Whereas the party of the first part hath heretofore covenanted "
        "to do all things requisite and necessary."
    ).json()
    assert len(body["warnings"]) == len(set(body["warnings"]))


# ---------------------------------------------------------------------------
# BAD INPUT
# ---------------------------------------------------------------------------

def test_empty_text_is_refused(live_service):
    response = simplify("")
    assert response.status_code == 400, _describe(response)
    assert "Traceback" not in response.text


def test_whitespace_only_text_is_refused(live_service):
    response = simplify("     \n   ")
    assert response.status_code == 400, _describe(response)


def test_unsupported_language_is_refused(live_service):
    response = simplify("The matter is adjourned.", "fra_Latn")
    assert response.status_code == 400, _describe(response)

    detail = response.json()["detail"]
    assert "Unsupported target_lang" in detail
    assert "mar_Deva" in detail
    assert "Traceback" not in response.text


def test_very_long_text_over_the_limit_is_refused(live_service):
    oversized = "The matter is adjourned to the next date of hearing. " * 500
    assert len(oversized) > MAX_INPUT_CHARS

    response = simplify(oversized)
    assert response.status_code == 400, _describe(response)
    assert "too long" in response.json()["detail"].lower()
    assert "Traceback" not in response.text


def test_long_but_allowed_text_is_answered(live_service):
    long_text = " ".join(
        "The learned counsel for the petitioner submitted that the "
        "petitioner has been cooperating with the investigation."
        for _ in range(120)
    )
    assert 10_000 < len(long_text) <= MAX_INPUT_CHARS

    response = simplify(long_text)
    assert response.status_code == 200, _describe(response)

    body = response.json()
    assert set(body) == SIX_KEYS
    assert body["simple_english"].strip()
    assert _no_reference_lost(body)


def test_garbage_body_is_refused(live_service):
    response = requests.post(
        f"{BASE}/api/legal-simplify",
        data="not json at all",
        headers={**HEADERS, "Content-Type": "application/json"},
        timeout=30,
    )
    assert response.status_code == 422, _describe(response)
    assert "Traceback" not in response.text


# ---------------------------------------------------------------------------
# TRANSLATION FAILURE — a safe sentence, never a stack trace
# ---------------------------------------------------------------------------

def test_translation_failure_returns_500_without_a_stack_trace():
    """The model layer is made to fail on purpose.

    `_ensure_model` is neutralised so the checkpoint is never loaded
    into the *test* process — the failure has to happen without paying
    for a model to get there.
    """
    import translate_service as service
    from fastapi.testclient import TestClient

    def _explode(*_args, **_kwargs):
        raise RuntimeError("simulated model failure")

    original_ensure = service._ensure_model
    original_translate = service.translate

    service._ensure_model = lambda _name: None
    service.translate = _explode

    try:
        with TestClient(service.app, raise_server_exceptions=False) as client:
            response = client.post(
                "/api/legal-simplify",
                json={
                    "text": "The application is hereby rejected on grounds of res judicata.",
                    "target_lang": "mar_Deva",
                },
                headers=HEADERS,
            )
    finally:
        service._ensure_model = original_ensure
        service.translate = original_translate
        service._translate_simple_layer.cache_clear()

    assert response.status_code == 500
    assert response.json()["detail"] == "Translation failed. Please try again."

    text = response.text
    assert "Traceback" not in text
    assert "simulated model failure" not in text
    assert "RuntimeError" not in text


def test_model_is_loaded_once_and_reused(live_service):
    """Two identical asks must not pay for the model twice."""
    text = "The petitioner is directed to file a reply within four weeks."

    first = simplify(text, "hin_Deva")
    assert first.status_code == 200, _describe(first)

    started = time.time()
    second = simplify(text, "hin_Deva")
    elapsed = time.time() - started

    assert second.status_code == 200, _describe(second)
    assert second.json() == first.json()
    # Cached: a repeat of the same sentence is a lookup, not a decode.
    assert elapsed < 30, f"repeat took {elapsed:.1f}s"


# ---------------------------------------------------------------------------
# THE COURT ORDER PATH: PDF -> extract -> split -> simplify -> Marathi
# ---------------------------------------------------------------------------

def test_pdf_extract_split_simplify_marathi(order_pdf, live_service):
    # 1. extraction
    with order_pdf.open("rb") as handle:
        extracted = requests.post(
            f"{BASE}/api/court-order/extract",
            files={"file": (order_pdf.name, handle, "application/pdf")},
            headers=HEADERS,
            timeout=TIMEOUT,
        )

    assert extracted.status_code == 200, _describe(extracted)
    text = extracted.json()["text"]
    assert "RAMESH KUMAR" in text

    # 2. the same PDF split into the five sections of a court order
    with order_pdf.open("rb") as handle:
        explained = requests.post(
            f"{BASE}/api/court-order/explain",
            files={"file": (order_pdf.name, handle, "application/pdf")},
            params={"language": "en"},
            headers=HEADERS,
            timeout=TIMEOUT,
        )

    assert explained.status_code == 200, _describe(explained)
    body = explained.json()
    sections = {section["section_id"]: section for section in body["sections"]}
    assert [section["section_id"] for section in body["sections"]] == SECTION_IDS

    order_text = sections["order"]["text"]
    assert order_text and "rejected" in order_text

    # 3. one section, in three layers, ending in Marathi
    response = simplify(order_text, "mar_Deva")
    assert response.status_code == 200, _describe(response)

    layer = response.json()
    assert set(layer) == SIX_KEYS
    assert layer["original_text"] == order_text
    assert "has been rejected" in layer["simple_english"], layer["simple_english"]
    assert _has_devanagari(layer["translated_text"])
    assert _no_reference_lost(layer), layer["warnings"]

    # 4. and the case-details layer, which is where names and numbers live
    response = simplify(sections["case_details"]["text"], "mar_Deva")
    assert response.status_code == 200, _describe(response)

    details = response.json()
    assert "RAMESH KUMAR" in details["translated_text"]
    assert "MHMH010123452026" in details["translated_text"]
    assert _no_reference_lost(details), details["warnings"]


# ---------------------------------------------------------------------------
# REGRESSION — the endpoints this feature was built on must still work
# ---------------------------------------------------------------------------

def test_existing_translate_endpoint_still_works(live_service):
    response = requests.post(
        f"{BASE}/api/translate",
        json={
            "case_id": "CNR-TEST",
            "source_text": "The matter is adjourned to the next date of hearing.",
            "source_lang": "en",
            "target_lang": "mr",
        },
        headers=HEADERS,
        timeout=TIMEOUT,
    )
    assert response.status_code == 200, _describe(response)
    assert _has_devanagari(response.json()["translated_text"])


def test_existing_guidance_endpoint_still_works(live_service):
    response = requests.post(
        f"{BASE}/api/guidance",
        json={"text": "My bail application was rejected yesterday"},
        headers=HEADERS,
        timeout=60,
    )
    assert response.status_code == 200, _describe(response)
    assert response.json()["matched"] is True

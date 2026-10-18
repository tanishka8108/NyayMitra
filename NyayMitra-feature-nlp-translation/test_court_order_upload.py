"""Court Order endpoints — upload pipeline, security, OCR, translation.

Run against a live NLP service (default :8001):

    .venv/bin/pytest test_court_order_upload.py -v

Everything except the exception-handler test talks to that service over
HTTP, exactly as the frontend does, so the contract being tested is the
one the browser sees. The exception-handler test imports the app in
process and adds a route that raises, because that is the only way to
prove a 500 comes back without a stack trace.

Fixtures are generated rather than committed: a text PDF, a scanned
(image-only) PDF, a partial order that is missing sections, a corrupt
PDF, something that is not a PDF at all, an oversized file and a PDF
carrying JavaScript/OpenAction indicators.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import requests

BASE = os.environ.get("NYAYMITRA_NLP_URL", "http://127.0.0.1:8001").rstrip("/")
API_KEY = os.environ.get("NYAYMITRA_NLP_KEY", "nyaymitra-local-test-2026")
HEADERS = {"Authorization": f"Bearer {API_KEY}"}
TIMEOUT = 600

FIXTURE_DIR = Path(os.environ.get("NYAYMITRA_TEST_TMP", "/tmp")) / "nyaymitra_court_fixtures"

SECTION_IDS = ["case_details", "proceedings", "order", "signatures", "certification"]
SECTION_TITLES = {
    "case_details": "Case Details",
    "proceedings": "Proceedings and Discussion",
    "order": "Order",
    "signatures": "Signatures",
    "certification": "Document Certification",
}

FULL_ORDER_LINES = [
    "IN THE COURT OF THE ADDITIONAL DISTRICT JUDGE, KHED",
    "Case Type: Criminal Misc Application",
    "Filing Number: 123/2026",
    "Filing Date: 01-01-2026",
    "Registration Number: 123/2026",
    "Petitioner: RAMESH KUMAR versus Respondent: STATE OF MAHARASHTRA",
    "1. The petitioner has filed this application seeking anticipatory bail in connection with an offence punishable under Section 306 of the Bharatiya Nyaya Sanhita.",
    "2. The learned counsel for the petitioner submitted that the petitioner has been cooperating with the investigation and undertook to appear whenever called upon to do so.",
    "ORDER",
    "3. Heard learned counsel for the petitioner in the presence of the learned public prosecutor for the State.",
    "4. The application is hereby rejected. Liberty is reserved to the petitioner to approach the proper forum in accordance with law.",
    "ORDERED that the application be rejected.",
    "LAST WORD: 25-09-2026",
    "A. SHARMA",
    "JUDGE",
    "Whether speaking/reasoned: Yes",
    "Whether reportable: No",
    "I attest to the accuracy and integrity of this document",
]

SHORT_ORDER_LINES = [
    "IN THE COURT OF THE SESSIONS JUDGE, PUNE",
    "Case Type: Civil Appeal 45/2026",
    "Filing Date: 02-02-2026",
    "1. The appeal is listed for final hearing today.",
    "ORDER",
    "2. The appeal is adjourned to the next date of hearing.",
    "B. IYER",
    "JUDGE",
]

PARTIAL_ORDER_LINES = [
    "IN THE COURT OF THE JUNIOR CIVIL JUDGE, RAJAHMUNDRY",
    "Case Type: Original Suit 7/2026",
    "Filing Number: 7/2026",
    "Filing Date: 03-03-2026",
    "Petitioner: SUNITA DEVI versus Respondent: MUNICIPAL CORPORATION",
]


# ---------------------------------------------------------------------------
# FIXTURES
# ---------------------------------------------------------------------------

def _text_pdf(path: Path, lines: list[str]) -> Path:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

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


def _scanned_pdf(path: Path, lines: list[str]) -> Path:
    """An image-only PDF, the way a photocopied order arrives."""
    from PIL import Image, ImageDraw, ImageFont

    width, height = 1600, 2200

    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 44
        )
    except OSError:
        font = ImageFont.load_default(size=44)

    image = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(image)
    y = 140

    for line in lines:
        draw.text((90, y), line, font=font, fill=0)
        y += 90

    image.convert("RGB").save(path, "PDF", resolution=200.0)
    return path


@pytest.fixture(scope="session")
def fixtures(tmp_path_factory) -> dict[str, Path]:
    directory = FIXTURE_DIR
    directory.mkdir(parents=True, exist_ok=True)

    built = {
        "full": _text_pdf(directory / "full_order.pdf", FULL_ORDER_LINES),
        "short": _text_pdf(directory / "short_order.pdf", SHORT_ORDER_LINES),
        "partial": _text_pdf(directory / "partial_order.pdf", PARTIAL_ORDER_LINES),
        "scanned": _scanned_pdf(directory / "scanned_order.pdf", SHORT_ORDER_LINES),
    }

    built["corrupt"] = directory / "corrupt.pdf"
    built["corrupt"].write_bytes(b"%PDF-1.4\nthis is not really a pdf body\n")

    built["not_pdf"] = directory / "notes.txt"
    built["not_pdf"].write_bytes(b"This is a plain text file, not a court order PDF.")

    # Valid PDF, then trailing bytes carrying the indicators the scanner
    # looks for — a real malicious PDF hides them the same way.
    suspicious = built["full"].read_bytes()
    suspicious += b"\n% /OpenAction << /S /JavaScript >> /JS /Launch\n"
    built["suspicious"] = directory / "suspicious.pdf"
    built["suspicious"].write_bytes(suspicious)

    # One byte over the limit: refused while being read, never parsed.
    built["oversized"] = directory / "oversized.pdf"
    built["oversized"].write_bytes(
        b"%PDF-1.4\n" + b"0" * (10 * 1024 * 1024 + 1)
    )

    return built


@pytest.fixture(scope="session")
def live_service():
    """Wait for the service rather than race it — it is started by hand
    or by CI moments before the suite runs."""
    import time

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


def _upload(path: Path, *, language: str | None = None, auth: bool = True):
    with path.open("rb") as handle:
        files = {"file": (path.name, handle, "application/pdf")}
        params = {"language": language} if language else None
        headers = HEADERS if auth else {}
        return requests.post(
            f"{BASE}/api/court-order/explain",
            files=files,
            params=params,
            headers=headers,
            timeout=TIMEOUT,
        )


def _describe(response) -> str:
    return f"status={response.status_code} body={response.text[:300]}"


def _by_id(body: dict) -> dict:
    return {section["section_id"]: section for section in body["sections"]}


def _has_devanagari(text: str) -> bool:
    return any("ऀ" <= char <= "ॿ" for char in text)


# ---------------------------------------------------------------------------
# SECURITY / VALIDATION
# ---------------------------------------------------------------------------

def test_explain_requires_api_key(fixtures, live_service):
    response = _upload(fixtures["full"], auth=False)
    assert response.status_code == 401, _describe(response)


def test_explain_rejects_non_pdf(fixtures, live_service):
    response = _upload(fixtures["not_pdf"])
    assert response.status_code == 400, _describe(response)
    assert "PDF" in response.json()["detail"]
    assert "Traceback" not in response.text


def test_explain_rejects_corrupt_pdf(fixtures, live_service):
    response = _upload(fixtures["corrupt"])
    assert response.status_code == 400, _describe(response)
    detail = response.json()["detail"]
    assert "Traceback" not in detail
    assert any(word in detail.lower() for word in ("corrupt", "read", "valid"))


def test_explain_rejects_oversized_pdf(fixtures, live_service):
    response = _upload(fixtures["oversized"])
    assert response.status_code == 400, _describe(response)
    assert "too large" in response.json()["detail"].lower()


def test_explain_rejects_suspicious_pdf(fixtures, live_service):
    response = _upload(fixtures["suspicious"])
    assert response.status_code == 400, _describe(response)

    detail = response.json()["detail"]
    # The scanner's own wording: generic on purpose, so the caller never
    # learns which indicators are checked.
    assert "security reasons" in detail
    assert "JavaScript" not in detail
    assert "OpenAction" not in detail
    assert "Traceback" not in detail


# ---------------------------------------------------------------------------
# THE PIPELINE
# ---------------------------------------------------------------------------

def test_explain_full_pdf_returns_all_five_sections(fixtures, live_service):
    response = _upload(fixtures["full"])
    assert response.status_code == 200, _describe(response)

    body = response.json()
    assert body["success"] is True
    assert body["filename"] == "full_order.pdf"
    assert body["language"] == "en"

    metadata = body["metadata"]
    assert metadata["ocr_used"] is False
    assert metadata["page_count"] >= 1
    assert metadata["security_scan"] == {"scanned": True, "status": "clean"}
    assert metadata["sections_found"] == 5
    assert metadata["text_characters"] > 200

    assert [section["section_id"] for section in body["sections"]] == SECTION_IDS

    for section in body["sections"]:
        assert section["title"] == SECTION_TITLES[section["section_id"]]
        assert section["available"] is True, section
        assert section["text"], section
        assert section["explanation"], section

    sections = _by_id(body)
    assert "RAMESH KUMAR" in sections["case_details"]["text"]
    assert "cooperating with the investigation" in sections["proceedings"]["text"]
    assert "hereby rejected" in sections["order"]["text"]
    assert "JUDGE" in sections["signatures"]["text"].upper()
    assert "attest to the accuracy" in sections["certification"]["text"].lower()

    # Top-level fields the pasted-text flow returns, so one screen can
    # render either response.
    assert body["summary"]
    assert isinstance(body["points"], list) and body["points"]
    assert isinstance(body["key_dates"], list) and body["key_dates"]
    assert isinstance(body["terms"], list)
    assert "not legal advice" in body["disclaimer"]


def test_explain_partial_pdf_reports_missing_sections(fixtures, live_service):
    response = _upload(fixtures["partial"])
    assert response.status_code == 200, _describe(response)

    body = response.json()
    sections = _by_id(body)

    assert [section["section_id"] for section in body["sections"]] == SECTION_IDS

    assert sections["case_details"]["available"] is True
    assert "SUNITA DEVI" in sections["case_details"]["text"]

    for missing in ("proceedings", "order", "signatures", "certification"):
        section = sections[missing]
        assert section["available"] is False, section
        assert section["text"] is None
        assert section["paragraphs"] == []
        assert section["explanation"] == []
        assert section["note"] == "Not available in the document."

    assert body["metadata"]["sections_found"] == 1


def test_explain_scanned_pdf_uses_ocr(fixtures, live_service):
    response = _upload(fixtures["scanned"])
    assert response.status_code == 200, _describe(response)

    body = response.json()
    metadata = body["metadata"]

    assert metadata["ocr_used"] is True
    assert metadata["extraction"]["ocr_pages"], metadata
    assert metadata["page_count"] >= 1
    assert metadata["text_characters"] > 60, metadata

    # The text really came from pixels, so the OCR result is asserted on
    # content, not just on the flag saying a scan happened.
    joined = " ".join(
        section["text"] or "" for section in body["sections"] if section["available"]
    )
    assert "SESSIONS JUDGE" in joined.upper()
    assert body["sections"][0]["available"] is True


# ---------------------------------------------------------------------------
# LANGUAGES
# ---------------------------------------------------------------------------

def test_explain_english_document(fixtures, live_service):
    response = _upload(fixtures["short"], language="en")
    assert response.status_code == 200, _describe(response)

    body = response.json()
    assert body["language"] == "en"
    assert "translation" not in body

    # The order says "adjourned"; the plain-language heading it earns is
    # the postponement one, which is the point of the exercise.
    headings = " ".join(point["heading"].lower() for point in body["points"])
    assert "postponed" in headings, headings


def test_explain_hindi_translation(fixtures, live_service):
    response = _upload(fixtures["short"], language="hi")
    assert response.status_code == 200, _describe(response)

    body = response.json()
    assert body["language"] == "hi"

    translation = body.get("translation") or {}
    assert translation.get("applied") is True, body.get("translation")

    translated = [
        section.get("translated_text")
        or ""
        for section in body["sections"]
        if section["available"]
    ]
    assert translated and all(translated)
    assert _has_devanagari(" ".join(translated))
    assert _has_devanagari(body["summary"])


def test_explain_marathi_translation(fixtures, live_service):
    response = _upload(fixtures["short"], language="mr")
    assert response.status_code == 200, _describe(response)

    body = response.json()
    assert body["language"] == "mr"

    translation = body.get("translation") or {}
    assert translation.get("applied") is True, body.get("translation")

    translated = [
        section.get("translated_text")
        or ""
        for section in body["sections"]
        if section["available"]
    ]
    assert translated and all(translated)
    assert _has_devanagari(" ".join(translated))


# ---------------------------------------------------------------------------
# THE THREE LAYERS — legal text → simple English → translation
# ---------------------------------------------------------------------------

def test_simple_english_rewrites_the_legalese_not_the_content():
    """The middle layer is a rewrite of *wording* — no service needed."""
    from court_order_simple_english import simplify_text

    plain = simplify_text(
        "The matter is adjourned to 15-05-2026. The learned counsel "
        "for the petitioner may prefer an appeal."
    )

    assert "The hearing has been postponed to 15-05-2026." in plain
    assert "The lawyer for the petitioner may file an appeal." in plain
    assert "adjourned" not in plain

    # Dates, case numbers and party names pass through byte for byte.
    untouched = (
        "Petitioner: RAMESH KUMAR versus Respondent: STATE OF MAHARASHTRA"
    )
    assert simplify_text(untouched) == untouched

    # Nothing with no plain equivalent is guessed at.
    assert simplify_text("Nothing here is legalese.") == (
        "Nothing here is legalese."
    )

    assert simplify_text("") == ""
    assert simplify_text(None) == ""


def test_explain_three_layers_english(fixtures, live_service):
    response = _upload(fixtures["short"])
    assert response.status_code == 200, _describe(response)

    body = response.json()
    layers = body["layers"]

    assert layers["legal"], layers
    assert layers["simple"], layers
    assert layers["translated"] is None, "English asks for no third layer"

    # The document's own middle layer is the plain reading.
    assert "postponed" in layers["simple"]

    for section in body["sections"]:
        if not section["available"]:
            assert section["layers"] == {
                "legal": None,
                "simple": None,
                "translated": None,
            }
            assert section["simple_text"] is None
            continue

        assert section["layers"]["legal"] == section["text"]
        assert section["simple_text"] == section["layers"]["simple"]
        assert section["layers"]["translated"] is None

    # The postponement, wherever the splitter put it: written one way
    # in step one and the plain way in step two.
    legal = " ".join(
        section["layers"]["legal"] or "" for section in body["sections"]
    )
    simple = " ".join(
        section["layers"]["simple"] or "" for section in body["sections"]
    )

    assert "adjourned" in legal
    assert "postponed" in simple
    assert "adjourned" not in simple
    assert "next hearing date" in simple, simple


def test_explain_three_layers_marathi(fixtures, live_service):
    response = _upload(fixtures["short"], language="mr")
    assert response.status_code == 200, _describe(response)

    body = response.json()
    assert body["language"] == "mr"

    layers = body["layers"]
    assert layers["legal"] and layers["simple"] and layers["translated"]
    assert _has_devanagari(layers["translated"])

    # Steps one and two stay in English — the model only ever sees
    # the simple layer, never the legalese.
    assert not _has_devanagari(layers["legal"])
    assert not _has_devanagari(layers["simple"])
    assert (body.get("translation") or {}).get("layer") == "simple"

    for section in body["sections"]:
        if not section["available"]:
            continue

        assert section["layers"]["legal"] == section["text"]
        assert section["simple_text"] == section["layers"]["simple"]
        assert _has_devanagari(section["layers"]["translated"] or "")
        # The section body the screen has always shown is step three.
        assert section["translated_text"] == section["layers"]["translated"]


# ---------------------------------------------------------------------------
# THE PASTED-TEXT PATH (regression — this is what shipped before)
# ---------------------------------------------------------------------------

def test_explain_pasted_text_shape(fixtures, live_service):
    text = (
        "The application for bail is hereby rejected. The petitioner may "
        "prefer an appeal within thirty days. Costs are reserved."
    )
    response = requests.post(
        f"{BASE}/api/court-order/explain",
        json={"text": text, "filename": "pasted.txt"},
        headers=HEADERS,
        timeout=TIMEOUT,
    )

    assert response.status_code == 200, _describe(response)
    body = response.json()

    # Two fields were added to this answer on purpose — `language` and
    # `layers` — so a pasted order is shown in the same three steps an
    # uploaded one is. Everything else the shipped shape had is here.
    assert set(body) == {
        "filename",
        "summary",
        "points",
        "key_dates",
        "terms",
        "disclaimer",
        "language",
        "layers",
    }
    assert body["filename"] == "pasted.txt"
    assert body["summary"]
    assert body["points"][0]["heading"]
    assert body["key_dates"] == []
    assert "not legal advice" in body["disclaimer"]

    assert body["language"] == "en"
    assert body["layers"]["legal"]
    assert body["layers"]["simple"]
    assert body["layers"]["translated"] is None

    # Step two is the plain reading of the order: no legalese, same
    # meaning — the rules call the rejection "was refused".
    assert "hereby" in body["layers"]["legal"]
    assert "hereby" not in body["layers"]["simple"]
    assert "refused" in body["layers"]["simple"]


def test_explain_pasted_text_requires_words(fixtures, live_service):
    response = requests.post(
        f"{BASE}/api/court-order/explain",
        json={"text": "   ", "filename": "empty.txt"},
        headers=HEADERS,
        timeout=TIMEOUT,
    )
    assert response.status_code == 400, _describe(response)


def test_explain_pasted_text_three_layers_marathi(fixtures, live_service):
    response = requests.post(
        f"{BASE}/api/court-order/explain",
        json={
            "text": (
                "The matter is adjourned to the next date of hearing. "
                "The petitioner may prefer an appeal."
            ),
            "filename": "pasted.txt",
            "language": "mr",
        },
        headers=HEADERS,
        timeout=TIMEOUT,
    )

    assert response.status_code == 200, _describe(response)
    body = response.json()

    assert body["language"] == "mr"
    assert body["layers"]["legal"]
    assert body["layers"]["simple"]
    assert "adjourned" in body["layers"]["legal"]
    assert "postponed" in body["layers"]["simple"]

    assert _has_devanagari(body["layers"]["translated"] or "")
    assert _has_devanagari(body["summary"])
    assert (body.get("translation") or {}).get("applied") is True


def test_explain_pasted_text_unknown_language_stays_english(
    fixtures, live_service,
):
    response = requests.post(
        f"{BASE}/api/court-order/explain",
        json={
            "text": "The application for bail is hereby rejected.",
            "filename": "pasted.txt",
            "language": "klingon",
        },
        headers=HEADERS,
        timeout=TIMEOUT,
    )

    assert response.status_code == 200, _describe(response)
    body = response.json()

    assert body["language"] == "en"
    assert body["layers"]["translated"] is None
    assert "translation" not in body
    assert "hereby" not in body["layers"]["simple"]


def test_explain_rejects_garbage_body(fixtures, live_service):
    response = requests.post(
        f"{BASE}/api/court-order/explain",
        data=b"not json at all",
        headers={**HEADERS, "Content-Type": "application/json"},
        timeout=TIMEOUT,
    )
    assert response.status_code == 400, _describe(response)
    assert "Traceback" not in response.text


# ---------------------------------------------------------------------------
# EXTRACTION (regression — same checks, now with validation and OCR)
# ---------------------------------------------------------------------------

def _extract(path: Path, auth: bool = True):
    with path.open("rb") as handle:
        files = {"file": (path.name, handle, "application/pdf")}
        return requests.post(
            f"{BASE}/api/court-order/extract",
            files=files,
            headers=HEADERS if auth else {},
            timeout=TIMEOUT,
        )


def test_extract_reads_text_pdf(fixtures, live_service):
    response = _extract(fixtures["full"])
    assert response.status_code == 200, _describe(response)

    body = response.json()
    assert body["ok"] is True
    assert body["needs_text"] is False
    assert "RAMESH KUMAR" in body["text"]
    assert body["ocr_used"] is False
    assert body["page_count"] >= 1


def test_extract_reads_scanned_pdf_with_ocr(fixtures, live_service):
    response = _extract(fixtures["scanned"])
    assert response.status_code == 200, _describe(response)

    body = response.json()
    assert body["ok"] is True, body
    assert body["ocr_used"] is True
    assert "SESSIONS JUDGE" in body["text"].upper()


def test_extract_rejects_corrupt_pdf(fixtures, live_service):
    response = _extract(fixtures["corrupt"])
    assert response.status_code == 400, _describe(response)
    assert "Traceback" not in response.text


def test_extract_rejects_suspicious_pdf(fixtures, live_service):
    response = _extract(fixtures["suspicious"])
    assert response.status_code == 400, _describe(response)
    assert "JavaScript" not in response.text


def test_extract_rejects_oversized_pdf(fixtures, live_service):
    response = _extract(fixtures["oversized"])
    assert response.status_code == 400, _describe(response)
    assert "too large" in response.json()["detail"].lower()


def test_extract_requires_api_key(fixtures, live_service):
    response = _extract(fixtures["full"], auth=False)
    assert response.status_code == 401, _describe(response)


# ---------------------------------------------------------------------------
# GUIDANCE (regression — shares this service and must keep working)
# ---------------------------------------------------------------------------

def test_guidance_still_matches(live_service):
    response = requests.post(
        f"{BASE}/api/guidance",
        json={"text": "My bail application was rejected yesterday"},
        headers=HEADERS,
        timeout=60,
    )

    assert response.status_code == 200, _describe(response)
    body = response.json()
    assert body["matched"] is True
    assert body["stage"]
    assert body["what_to_do_next"]
    assert body["candidates"] == []


# ---------------------------------------------------------------------------
# ERROR HANDLING — no stack trace ever reaches the caller
# ---------------------------------------------------------------------------

def test_unhandled_error_returns_json_without_traceback(live_service):
    import translate_service as service
    from fastapi.testclient import TestClient

    service.app.add_api_route(
        "/__test_boom", lambda: (_ for _ in ()).throw(ZeroDivisionError("boom")),
        methods=["GET"],
    )

    try:
        with TestClient(service.app, raise_server_exceptions=False) as client:
            response = client.get("/__test_boom")
    finally:
        service.app.router.routes = [
            route
            for route in service.app.router.routes
            if getattr(route, "path", "") != "/__test_boom"
        ]

    assert response.status_code == 500
    text = response.text
    assert "Traceback" not in text
    assert "ZeroDivision" not in text
    assert "boom" not in text
    assert "detail" in text

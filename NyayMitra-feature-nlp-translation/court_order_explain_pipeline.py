"""The uploaded-PDF path behind ``POST /api/court-order/explain``.

Order of operations, and why:

1. **Validation** (``upload_validation.validate_pdf_upload``) — size,
   MIME type and readability. A corrupt or password-protected file
   stops here.
2. **Security scan** (``pdf_security_scan``) — JavaScript, OpenAction
   and friends, before any parser touches the document.
3. **Text extraction** (pdfplumber) with an **OCR fallback**
   (``pdf_extraction_pipeline.ocr_fallback_for_page``, then
   ``ocr_preprocess`` when the first pass finds nothing) for pages that
   are a scan.
4. **Section splitting** (``court_order_section_splitter``) — Case
   Details, Proceedings, Order, Signatures, Document Certification.
5. **Explanation** (``court_order_explainer``) — the same rules the
   pasted-text path uses.
6. **The three layers** (``court_order_simple_english``) — every
   section and the document itself come back as *original legal
   text* → *simple English*, the middle layer being the order's own
   wording with only its legalese replaced.
7. **Optional translation** to Hindi or Marathi, passed in as a
   callable by the service so the model lifecycle stays there. The
   model is given the simple layer, not the legalese, so step three
   reads the way a person would say it.

The PDF itself is only ever read as bytes: it is written to a private
temporary file so the page renderer can seek it, and that file is
deleted whether the request succeeds or fails. Nothing in the document
is executed, and no document text is written to the logs.
"""

from __future__ import annotations

import io
import logging
import os
import tempfile
from typing import Any, Callable

from court_order_explainer import EXPLAIN_DISCLAIMER, explain_text, first_sentence
from court_order_section_splitter import split_court_order
from court_order_simple_english import build_layers, plain_summary
from court_order_translation_pipeline import build_splitter_input
from pdf_security_scan import PDFSecurityError, secure_validate_pdf
from upload_validation import PDF_MAX_SIZE_BYTES, UploadValidationError, validate_pdf_upload

logger = logging.getLogger("nyaymitra.court_order")

# The five sections a court order is read as, in reading order.
CANONICAL_SECTIONS = [
    ("case_details", "Case Details"),
    ("proceedings", "Proceedings and Discussion"),
    ("order", "Order"),
    ("signatures", "Signatures"),
    ("certification", "Document Certification"),
]

NOT_AVAILABLE_NOTE = "Not available in the document."

NO_TEXT_MESSAGE = (
    "No readable text could be extracted from this PDF, even with OCR. "
    "Upload a clearer scan, or paste the text of the order and it will "
    "be explained."
)

SUPPORTED_LANGUAGES = {"en", "hi", "mr"}
OCR_LANG = "eng+hin+mar"
OCR_CONFIDENCE_FLOOR = 30.0

TranslateFn = Callable[[str], str]


class CourtOrderUploadError(Exception):
    """A failure with a message that is safe to show the uploader."""


# ---------------------------------------------------------------------------
# EXTRACTION
# ---------------------------------------------------------------------------

def _ocr_one_page(temp_pdf: str, page_number: int) -> tuple[str, float]:
    """OCR one page of the temporary PDF, cheap pass first."""
    from pdf_extraction_pipeline import ocr_fallback_for_page

    try:
        text, confidence = ocr_fallback_for_page(
            temp_pdf, page_number, lang=OCR_LANG
        )
    except Exception as exc:  # noqa: BLE001 - OCR is best effort
        logger.warning("ocr page=%d direct pass failed: %r", page_number, exc)
        return "", 0.0

    text = (text or "").strip()

    if text and confidence >= OCR_CONFIDENCE_FLOOR:
        return text, confidence

    # The page is a scan, or the first pass came back muddy: deskew and
    # threshold the rendered page and try again.
    try:
        from ocr_preprocess import preprocess, run_ocr_with_confidence
        from pdf2image import convert_from_path

        pages = convert_from_path(
            temp_pdf, dpi=200, first_page=page_number, last_page=page_number
        )
        if not pages:
            return text, confidence

        image_path = f"{temp_pdf}.page{page_number}.png"
        try:
            pages[0].save(image_path)
            processed = preprocess(image_path)
            second_text, _low = run_ocr_with_confidence(processed, lang=OCR_LANG)
        finally:
            if os.path.exists(image_path):
                os.remove(image_path)
    except Exception as exc:  # noqa: BLE001 - preprocessing is optional
        logger.warning("ocr page=%d preprocess pass failed: %r", page_number, exc)
        return text, confidence

    second_text = (second_text or "").strip()

    # Keep whichever pass recognised more of the page.
    if len(second_text) > len(text):
        return second_text, confidence

    return text, confidence


def extract_document_text(data: bytes) -> dict[str, Any]:
    """Direct text per page, OCR for the pages that have none.

    Public because ``POST /api/court-order/extract`` reads documents
    the same way — one extraction path, not two that drift apart.
    """
    import pdfplumber

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        page_count = len(pdf.pages)
        direct = [(page.extract_text() or "").strip() for page in pdf.pages]

    ocr_used = False
    ocr_pages: list[int] = []
    ocr_failed = False
    texts: list[str] = []

    needs_ocr = [index + 1 for index, text in enumerate(direct) if not text]

    temp_pdf = ""
    try:
        if needs_ocr:
            handle = tempfile.NamedTemporaryFile(
                suffix=".pdf", delete=False
            )
            try:
                handle.write(data)
                temp_pdf = handle.name
            finally:
                handle.close()

        for index, text in enumerate(direct, start=1):
            if text:
                texts.append(text)
                continue

            ocr_used = True
            ocr_text, _confidence = _ocr_one_page(temp_pdf, index)

            if ocr_text:
                ocr_pages.append(index)
                texts.append(ocr_text)
            else:
                ocr_failed = True
                logger.info("ocr page=%d produced no text", index)
    finally:
        if temp_pdf and os.path.exists(temp_pdf):
            os.remove(temp_pdf)

    return {
        "page_count": page_count,
        "texts": texts,
        "ocr_used": ocr_used,
        "ocr_pages": ocr_pages,
        "ocr_failed": ocr_failed,
        "direct_pages": page_count - len(needs_ocr),
    }


# ---------------------------------------------------------------------------
# SECTIONS
# ---------------------------------------------------------------------------

def _section_body(section: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    """Flatten a split section into display text plus its paragraphs."""
    if "paragraphs" in section:
        paragraphs = [
            {
                "number": paragraph.get("number"),
                "text": paragraph.get("text") or "",
                "page_start": paragraph.get("page_start"),
                "page_end": paragraph.get("page_end"),
            }
            for paragraph in section.get("paragraphs") or []
        ]
        body = "\n\n".join(
            f"{item['number']}. {item['text']}".strip()
            for item in paragraphs
            if item["text"]
        )
        return body, paragraphs

    return (section.get("text") or "").strip(), []


def _build_sections(split_result: dict[str, Any]) -> list[dict[str, Any]]:
    """All five canonical sections, present or not.

    A missing section is returned rather than dropped: the caller asked
    for those five headings, and an empty one says "not found in this
    document" — which is information — where a gap would be read as a
    bug.
    """
    found = {
        section.get("section_id"): section
        for section in split_result.get("sections") or []
        if isinstance(section, dict)
    }

    sections: list[dict[str, Any]] = []

    for section_id, title in CANONICAL_SECTIONS:
        section = found.get(section_id)
        body, paragraphs = _section_body(section or {})

        if section is None or not body:
            sections.append(
                {
                    "section_id": section_id,
                    "title": title,
                    "available": False,
                    "text": None,
                    "simple_text": None,
                    "layers": build_layers(None),
                    "paragraphs": [],
                    "page_start": None,
                    "page_end": None,
                    "explanation": [],
                    "key_dates": [],
                    "note": NOT_AVAILABLE_NOTE,
                }
            )
            continue

        explained = explain_text(body, fallback_summary=title)

        # The middle layer of the three shown for this section: the
        # section's own wording, rewritten in plain words.
        layers = build_layers(body)

        sections.append(
            {
                "section_id": section_id,
                "title": title,
                "available": True,
                "text": body,
                "simple_text": layers["simple"],
                "layers": layers,
                "paragraphs": paragraphs,
                "page_start": section.get("page_start"),
                "page_end": section.get("page_end"),
                "explanation": explained["points"],
                "key_dates": explained["key_dates"],
                "note": "",
            }
        )

    return sections


# ---------------------------------------------------------------------------
# PIPELINE
# ---------------------------------------------------------------------------

def process_upload(
    data: bytes,
    filename: str,
    *,
    language: str = "en",
    translate: TranslateFn | None = None,
) -> dict[str, Any]:
    """Validate, scan, read, split and explain an uploaded court order."""
    if not data:
        raise CourtOrderUploadError("Uploaded file is empty.")

    if len(data) > PDF_MAX_SIZE_BYTES:
        raise CourtOrderUploadError(
            f"File too large. Maximum allowed size is "
            f"{PDF_MAX_SIZE_BYTES // (1024 * 1024)} MB."
        )

    # Order matters: refuse a hostile document before parsing it, and
    # validate type/structure before the scanner looks at bytes.
    try:
        validate_pdf_upload(data)
    except UploadValidationError as exc:
        raise CourtOrderUploadError(str(exc)) from exc

    try:
        secure_validate_pdf(data)
    except PDFSecurityError as exc:
        raise CourtOrderUploadError(str(exc)) from exc

    extraction = extract_document_text(data)
    page_count = extraction["page_count"]
    texts = extraction["texts"]

    full_text = "\n\n".join(text for text in texts if text).strip()

    if not full_text:
        raise CourtOrderUploadError(
            NO_TEXT_MESSAGE if extraction["ocr_used"] or extraction["ocr_failed"]
            else "This PDF contains no readable text."
        )

    split_result = split_court_order(
        build_splitter_input(
            [
                {"section_number": index + 1, "original_text": text}
                for index, text in enumerate(texts)
            ]
        )
    )

    sections = _build_sections(split_result)
    explained = explain_text(full_text, fallback_summary="Court order")

    language = (language or "en").strip().lower()
    if language not in SUPPORTED_LANGUAGES:
        language = "en"

    result: dict[str, Any] = {
        "success": True,
        "filename": filename,
        "language": language,
        "summary": explained["summary"],
        # The three layers the reader is shown, in order: the order as
        # it is written, what it says in plain English, and — when a
        # language was asked for — that plain English translated.
        "layers": build_layers(
            explained["summary"], plain=plain_summary(explained["points"])
        ),
        "sections": sections,
        "metadata": {
            "ocr_used": extraction["ocr_used"],
            "page_count": page_count,
            "security_scan": {"scanned": True, "status": "clean"},
            "extraction": {
                "direct_pages": extraction["direct_pages"],
                "ocr_pages": extraction["ocr_pages"],
            },
            "text_characters": len(full_text),
            "sections_found": sum(1 for item in sections if item["available"]),
        },
        # Same fields the pasted-text flow returns, so one screen can
        # render either without knowing which path ran.
        "points": explained["points"],
        "key_dates": explained["key_dates"],
        "terms": explained["terms"],
        "disclaimer": EXPLAIN_DISCLAIMER,
    }

    if language != "en" and translate is not None:
        result["translation"] = _translate_result(result, translate, language)

    return result


def _translate_result(
    result: dict[str, Any],
    translate: TranslateFn,
    language: str,
) -> dict[str, Any]:
    """The third layer: the simple English, translated.

    The model is handed the *plain* layer rather than the legalese —
    a sentence already in everyday words survives a small translation
    model, and a line of statutes often does not. Layer one (the order
    as written) stays in the response untouched, so the reader can
    step down all three and compare them.

    A model failure does not throw the English answer away: the text
    stays as it is and the response records why it is not translated.
    """
    try:
        layers = result.get("layers") or {}
        legal_summary = result["summary"]
        simple_summary = layers.get("simple") or legal_summary

        translated_summary = translate(legal_summary) or legal_summary
        result["summary"] = translated_summary

        layers["translated"] = (
            translated_summary
            if simple_summary == legal_summary
            else translate(simple_summary) or None
        )
        result["layers"] = layers

        for section in result["sections"]:
            if not section["available"] or not section["text"]:
                continue

            simple = section.get("simple_text") or section["text"]
            translated = translate(simple) or None

            section["translated_text"] = translated

            section_layers = section.get("layers")
            if isinstance(section_layers, dict):
                section_layers["translated"] = translated
    except Exception as exc:  # noqa: BLE001 - degrade, never lose the text
        logger.warning("court order translation failed: %r", exc)
        return {
            "requested": language,
            "applied": False,
            "reason": (
                "Translation could not be completed for this document. "
                "The English text above is complete."
            ),
        }

    return {
        "requested": language,
        "applied": True,
        "reason": "",
        # Which layer the model was given — always step two.
        "layer": "simple",
    }


def safe_filename(filename: str | None) -> str:
    """A loggable basename with nothing that could break a log line."""
    base = os.path.basename(filename or "").strip()
    cleaned = "".join(char for char in base if char.isprintable())
    return cleaned[:120] or "unnamed.pdf"

import io
import sys

import magic
import pdfplumber
from pdf2image import convert_from_path
import pytesseract

PDF_MAX_SIZE_BYTES = 10 * 1024 * 1024
ALLOWED_PDF_MIME_TYPES = {"application/pdf"}
LOW_CONFIDENCE_THRESHOLD = 60


class PDFValidationError(Exception):
    pass


def validate_pdf(file_bytes: bytes) -> None:
    if len(file_bytes) == 0:
        raise PDFValidationError("Uploaded file is empty.")

    if len(file_bytes) > PDF_MAX_SIZE_BYTES:
        raise PDFValidationError(
            f"File too large. Maximum allowed size is "
            f"{PDF_MAX_SIZE_BYTES // (1024 * 1024)} MB."
        )

    detected_type = magic.from_buffer(file_bytes, mime=True)

    if (
        detected_type not in ALLOWED_PDF_MIME_TYPES
        and not file_bytes.startswith(b"%PDF-")
    ):
        raise PDFValidationError(
            "File does not appear to be a valid PDF. "
            "Please upload a PDF document."
        )

    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            if len(pdf.pages) == 0:
                raise PDFValidationError("PDF appears to have no readable pages.")
    except PDFValidationError:
        raise
    except Exception:
        raise PDFValidationError(
            "This PDF could not be read. It may be corrupted or password-protected."
        )



def extract_text_direct(pdf_path):
    results = []

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_number, page in enumerate(pdf.pages, start=1):
                text = page.extract_text()
                results.append(
                    (page_number, text.strip() if text else None)
                )

    except Exception as e:
        raise PDFValidationError(
            "This PDF could not be read. It may be corrupted or malformed."
        ) from e

    return results


def ocr_fallback_for_page(pdf_path: str, page_number: int, lang: str = "eng+hin+mar"):
    pages = convert_from_path(
        pdf_path, dpi=200, first_page=page_number, last_page=page_number
    )
    page_img = pages[0]

    data = pytesseract.image_to_data(page_img, lang=lang, output_type=pytesseract.Output.DICT)
    words, confidences = [], []
    for i, word in enumerate(data["text"]):
        conf = int(data["conf"][i]) if data["conf"][i] not in ("-1", "") else -1
        if word.strip():
            words.append(word)
            if conf >= 0:
                confidences.append(conf)

    text = " ".join(words)
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0
    return text, avg_confidence


def process_pdf(pdf_path: str, lang: str = "eng+hin+mar"):
    with open(pdf_path, "rb") as f:
        file_bytes = f.read()

    validate_pdf(file_bytes)

    direct_results = extract_text_direct(pdf_path)
    sections = []

    for page_number, text in direct_results:
        if text:
            sections.append({
                "section_number": page_number,
                "original_text": text,
                "extraction_method": "direct",
                "ocr_confidence": None,
                "needs_review": False,
            })
        else:
            ocr_text, avg_conf = ocr_fallback_for_page(pdf_path, page_number, lang)
            sections.append({
                "section_number": page_number,
                "original_text": ocr_text,
                "extraction_method": "ocr_fallback",
                "ocr_confidence": round(avg_conf, 1),
                "needs_review": avg_conf < LOW_CONFIDENCE_THRESHOLD,
            })

    return sections


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python pdf_extraction_pipeline.py <pdf_path>")
        sys.exit(1)

    pdf_path = sys.argv[1]

    try:
        sections = process_pdf(pdf_path)
    except PDFValidationError as e:
        print(f"Validation failed: {e}")
        sys.exit(1)

    print(f"Extracted {len(sections)} page(s) from {pdf_path}\n")
    for sec in sections:
        print(f"--- Page {sec['section_number']} (method: {sec['extraction_method']}) ---")
        if sec["ocr_confidence"] is not None:
            flag = " [NEEDS REVIEW]" if sec["needs_review"] else ""
            print(f"OCR confidence: {sec['ocr_confidence']}%{flag}")
        print(sec["original_text"][:500])
        print()

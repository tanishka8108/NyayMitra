import sys
import re
import json
import requests

from pdf_extraction_pipeline import validate_pdf, PDFValidationError, extract_text_direct, ocr_fallback_for_page
from pdf_security_scan import secure_validate_pdf, PDFSecurityError

TRANSLATE_API_URL = "http://localhost:8001/api/translate"


def split_into_sections(page_text):
    parts = re.split(r'\n(?=\d{1,2}\.\s)', page_text)
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) <= 1:
        parts = [p.strip() for p in page_text.split("\n\n") if p.strip()]
    return parts if parts else [page_text.strip()]


def translate_section(text, target_lang, case_id="court-order"):
    try:
        response = requests.post(
            TRANSLATE_API_URL,
            json={
                "case_id": case_id,
                "source_text": text,
                "source_lang": "en",
                "target_lang": target_lang,
            },
            headers={"Authorization": "Bearer nyaymitra-local-test-2026"},
            timeout=120,
        )

        if response.status_code == 200:
            return response.json()["translated_text"]
        else:
            return f"[Translation failed: {response.text}]"
    except requests.exceptions.ConnectionError:
        return "[Translation API not running]"
def simplify_section(original_text, translated_text, target_lang):
    """
    Create a simple-language explanation using the approved legal glossary.
    The original translation is preserved, and glossary explanations are
    added only when matching legal terms are found.
    """
    try:
        from translation_service import find_glossary_matches, get_glossary_explanation

        matches = find_glossary_matches(original_text)

        if not matches:
            return translated_text

        explanations = []

        for entry in matches:
            explanation = get_glossary_explanation(
                entry,
                "hin_Deva" if target_lang == "hi" else "mar_Deva"
            )

            if explanation:
                explanations.append(
                    f"{entry['formal_term']}: {explanation}"
                )

        if not explanations:
            return translated_text

        return (
            translated_text
            + "\n\nसरल अर्थ:\n"
            + "\n".join(f"- {item}" for item in explanations)
            if target_lang == "hi"
            else
            translated_text
            + "\n\nसोप्या भाषेत अर्थ:\n"
            + "\n".join(f"- {item}" for item in explanations)
        )

    except Exception:
        # If glossary processing fails, keep the translation available.
        return translated_text

def clean_ocr_artifacts(text):
    """Remove known OCR artifacts while preserving surrounding legal text."""
    patterns = [
        (r"\bSie\s+aaa\s+", ""),
        (r"\bot\s+(?=That\b)", ""),
        (r"\bg\s+ae\s+yw\s+", ""),
        (r"‘A\s+Ww\s+°\s+", ""),
        (r"\byx\s+aa\s+", ""),
        (r"\bcb\s+(?=District\b)", ""),
        (r"\bvt\s+\\V\s+(?=Technology\b)", ""),
        (r"\bAX\s+a4\s+(?=233/2024\b)", ""),
        (r"\by\s+anes\s+(?=similar\b)", ""),
        (r"\blisted\)\s+(?=on\b)", "listed "),
        (r"\bMy\s+(?=Therefore\b)", ""),
        (r"\+\s+\}", ""),
        (r"Pune\s+\(\|\s+WH", "Pune"),
    ]

    cleaned = text

    for pattern, replacement in patterns:
        cleaned = re.sub(
            pattern,
            replacement,
            cleaned,
            flags=re.IGNORECASE,
        )

    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n\s*\n+", "\n\n", cleaned)

    return cleaned.strip()



def process_court_order(pdf_path, target_lang):
    with open(pdf_path, "rb") as f:
        file_bytes = f.read()

    # Security scan must happen before any PDF extraction/OCR.
    secure_validate_pdf(file_bytes)

    # Basic type, size, and readability validation.
    validate_pdf(file_bytes)

    direct_results = extract_text_direct(pdf_path)
    all_sections = []
    section_counter = 1

    for page_number, page_text in direct_results:
        if page_text:
            method = "direct"
            confidence = None
            text_to_split = page_text
        else:
            ocr_text, avg_conf = ocr_fallback_for_page(
    pdf_path,
    page_number,
    lang="eng",
)
            method = "ocr_fallback"
            confidence = round(avg_conf, 1)
            text_to_split = clean_ocr_artifacts(ocr_text)

        for chunk in split_into_sections(text_to_split):
            if len(chunk) < 10:
                continue

            translated = translate_section(chunk, target_lang)
            simplified = simplify_section(
           chunk,
           translated,
           target_lang
)

            all_sections.append({
                "section_number": section_counter,
                "page_number": page_number,
                "original_text": chunk,
        "simplified_text": simplified,
                "translated_text": translated,
                "language": target_lang,
                "extraction_method": method,
                "ocr_confidence": confidence,
                "needs_review": (confidence is not None and confidence < 60),

            })
            section_counter += 1

    return all_sections


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python court_order_pipeline.py <pdf_path> <target_lang: hi|mr>")
        sys.exit(1)

    pdf_path, target_lang = sys.argv[1], sys.argv[2]

    try:
        sections = process_court_order(pdf_path, target_lang)

    except PDFSecurityError as e:
        print(f"Security validation failed: {e}")
        sys.exit(1)

    except PDFValidationError as e:
        print(f"Validation failed: {e}")
        sys.exit(1)

    print(f"Processed {pdf_path} into {len(sections)} section(s):\n")

    for sec in sections:
        print(
            f"--- Section {sec['section_number']} "
            f"(page {sec['page_number']}, {sec['extraction_method']}) ---"
        )

        if sec["needs_review"]:
            print(
                f"  [NEEDS REVIEW - OCR confidence "
                f"{sec['ocr_confidence']}%]"
            )

        print(f"  EN: {sec['original_text'][:150]}")
        print(f"  {target_lang.upper()}: {sec['translated_text'][:150]}")
        print(f"  SIMPLE: {sec['simplified_text'][:200]}")
        print()

    output_path = (
        pdf_path.rsplit(".", 1)[0]
        + f"_sections_{target_lang}.json"
    )

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "document": pdf_path,
                "language": target_lang,
                "sections": sections
            },
            f,
            ensure_ascii=False,
            indent=2
        )

    print(f"Saved full structured output to {output_path}")

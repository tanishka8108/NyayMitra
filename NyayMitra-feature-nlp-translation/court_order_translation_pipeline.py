import json
import sys
from pathlib import Path

from pdf_extraction_pipeline import process_pdf
from court_order_section_splitter import split_court_order
from translation_service import translate_with_glossary


def build_splitter_input(extracted_pages):
    """
    Convert PDF extraction/OCR output into the page-marker
    format expected by the court-order section splitter.
    """

    lines = []

    for page in extracted_pages:
        page_number = page["section_number"]
        text = page.get("original_text") or ""

        lines.append(f"===== Page {page_number} =====\n")

        if text.strip():
            lines.extend(
                line + "\n"
                for line in text.splitlines()
                if line.strip()
            )

    return lines


def translate_section(section, target_language):
    """
    Translate legal content while preserving the section structure.
    """

    translated_section = {
        "section_id": section["section_id"],
        "title": section["title"],
        "page_start": section.get("page_start"),
        "page_end": section.get("page_end"),
    }

    # Sections containing paragraphs
    if "paragraphs" in section:

        translated_paragraphs = []

        for paragraph in section["paragraphs"]:

            result = translate_with_glossary(
                paragraph["text"],
                "eng_Latn",
                target_language
            )

            translated_paragraphs.append({
                "number": paragraph["number"],
                "page_start": paragraph.get("page_start"),
                "page_end": paragraph.get("page_end"),
                "original_text": paragraph["text"],
                "translated_text": result["translated_text"],
                "glossary_matches": result["glossary_matches"]
            })

        translated_section["paragraphs"] = translated_paragraphs

    # Sections containing normal text
    elif "text" in section:

        result = translate_with_glossary(
            section["text"],
            "eng_Latn",
            target_language
        )

        translated_section["original_text"] = section["text"]
        translated_section["translated_text"] = result["translated_text"]
        translated_section["glossary_matches"] = result["glossary_matches"]

    return translated_section


def process_court_order(pdf_path, target_language="hin_Deva"):
    """
    Complete pipeline:

    PDF
      -> validation
      -> direct extraction / OCR
      -> section splitting
      -> translation
      -> glossary
    """

    print("Step 1: Extracting text / running OCR...")

    extracted_pages = process_pdf(pdf_path)

    print("Step 2: Preparing text for section splitting...")

    splitter_lines = build_splitter_input(extracted_pages)

    print("Step 3: Splitting court order into sections...")

    split_result = split_court_order(splitter_lines)

    print(
        f"Found {len(split_result['sections'])} sections."
    )

    print("Step 4: Translating sections...")

    translated_sections = []

    for section in split_result["sections"]:

        print(
            f"  Translating: {section['title']}"
        )

        translated_sections.append(
            translate_section(
                section,
                target_language
            )
        )

    return {
        "target_language": target_language,
        "sections": translated_sections
    }


def main():

    if len(sys.argv) < 2:

        print(
            "Usage: python3 court_order_translation_pipeline.py "
            "<pdf_path> [target_language]"
        )

        print(
            "Example:"
        )

        print(
            "python3 court_order_translation_pipeline.py "
            "court_order.pdf hin_Deva"
        )

        sys.exit(1)

    pdf_path = sys.argv[1]

    target_language = (
        sys.argv[2]
        if len(sys.argv) >= 3
        else "hin_Deva"
    )

    if target_language not in {
        "hin_Deva",
        "mar_Deva"
    }:

        print(
            "Unsupported target language."
        )

        print(
            "Use: hin_Deva or mar_Deva"
        )

        sys.exit(1)

    result = process_court_order(
        pdf_path,
        target_language
    )

    output_file = (
        Path(pdf_path).stem
        + "_translated_"
        + target_language
        + ".json"
    )

    with open(
        output_file,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            result,
            f,
            indent=4,
            ensure_ascii=False
        )

    print()
    print(
        f"Translation pipeline completed."
    )

    print(
        f"Output saved to: {output_file}"
    )


if __name__ == "__main__":
    main()

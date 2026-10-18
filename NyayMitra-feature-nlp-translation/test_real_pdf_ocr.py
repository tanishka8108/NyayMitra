import sys
from pdf2image import convert_from_path
import pytesseract

def ocr_pdf(pdf_path, lang="eng+hin+mar"):
    print(f"Converting {pdf_path} to images...")
    pages = convert_from_path(pdf_path, dpi=300)
    print(f"Found {len(pages)} page(s).\n")

    all_text = []
    for i, page_img in enumerate(pages, start=1):
        print(f"--- OCR on page {i} ---")
        text = pytesseract.image_to_string(page_img, lang=lang)
        print(text)
        all_text.append(f"===== Page {i} =====\n{text}")

    with open("real_pdf_ocr_output.txt", "w", encoding="utf-8") as f:
        f.write("\n\n".join(all_text))
    print("\nSaved full output to real_pdf_ocr_output.txt")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_real_pdf_ocr.py <pdf_path>")
        sys.exit(1)
    ocr_pdf(sys.argv[1])

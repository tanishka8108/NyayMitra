from PIL import Image, ImageDraw, ImageFont
import pytesseract
import os

DEVANAGARI_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
]
LATIN_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
]

def get_font(candidates, size):
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    raise FileNotFoundError(f"No font found among: {candidates}")

def is_devanagari(line):
    return any('\u0900' <= ch <= '\u097F' for ch in line)

LINES = [
    "IN THE COURT OF THE DISTRICT JUDGE",
    "Case No. 4521/2026",
    "Order dated: 15.09.2026",
    "",
    "मामला बहस के लिए सूचीबद्ध है",
    "प्रतिवादी को नोटिस जारी किया गया है",
    "",
    "प्रकरण दिनांक 15.09.2026 रोजी अंतिम सुनावणीसाठी येत आहे",
    "",
    "Application for stay REJECTED.",
    "Next date of hearing: 20.10.2026",
]

def build_test_image(path="court_order_test.png"):
    latin_font = get_font(LATIN_FONT_CANDIDATES, 32)
    deva_font = get_font(DEVANAGARI_FONT_CANDIDATES, 32)

    img = Image.new("RGB", (1200, 80 + 55 * len(LINES)), "white")
    draw = ImageDraw.Draw(img)

    y = 40
    for line in LINES:
        font = deva_font if is_devanagari(line) else latin_font
        draw.text((50, y), line, font=font, fill="black")
        y += 55

    img.save(path)
    print(f"Test image saved to {path}")
    return path

def run_ocr(path):
    return pytesseract.image_to_string(Image.open(path), lang="eng+hin+mar")

if __name__ == "__main__":
    img_path = build_test_image()
    print("\nRunning Tesseract OCR (eng+hin+mar)...\n")
    extracted = run_ocr(img_path)
    print("----- OCR OUTPUT -----")
    print(extracted)
    print("----------------------")
    with open("ocr_output.txt", "w", encoding="utf-8") as f:
        f.write(extracted)
    print("\nSaved OCR output to ocr_output.txt")

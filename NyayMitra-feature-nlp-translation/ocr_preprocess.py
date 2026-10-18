import cv2
import numpy as np
import pytesseract
from PIL import Image

def deskew(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
    gray = cv2.bitwise_not(gray)
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    coords = np.column_stack(np.where(thresh > 0))
    if len(coords) == 0:
        return image
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
    (h, w) = image.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(image, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    return rotated

def denoise_and_threshold(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
    denoised = cv2.fastNlMeansDenoising(gray, h=15)
    thresh = cv2.adaptiveThreshold(denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, blockSize=31, C=15)
    return thresh

def upscale_if_small(image, min_width=1500):
    h, w = image.shape[:2]
    if w < min_width:
        scale = min_width / w
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    return image

def preprocess(image_path):
    image = cv2.imread(image_path)
    image = upscale_if_small(image)
    image = deskew(image)
    processed = denoise_and_threshold(image)
    return processed

def run_ocr_with_confidence(image, lang="eng+hin+mar"):
    pil_img = Image.fromarray(image)
    data = pytesseract.image_to_data(pil_img, lang=lang, output_type=pytesseract.Output.DICT)
    words = []
    low_confidence_words = []
    for i, word in enumerate(data["text"]):
        conf = int(data["conf"][i]) if data["conf"][i] != "-1" else -1
        if word.strip():
            words.append(word)
            if 0 <= conf < 60:
                low_confidence_words.append((word, conf))
    full_text = " ".join(words)
    return full_text, low_confidence_words

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python ocr_preprocess.py <path_to_image>")
        sys.exit(1)
    img_path = sys.argv[1]
    print(f"Preprocessing {img_path} ...")
    processed = preprocess(img_path)
    cv2.imwrite("preprocessed_debug.png", processed)
    print("Saved preprocessed_debug.png for visual inspection")
    print("\nRunning OCR on preprocessed image...\n")
    text, low_conf = run_ocr_with_confidence(processed)
    print("----- OCR TEXT -----")
    print(text)
    print("---------------------")
    if low_conf:
        print(f"\nWARNING: {len(low_conf)} low-confidence word(s) - review these manually:")
        for word, conf in low_conf:
            print(f"  '{word}' (confidence: {conf}%)")
    else:
        print("\nNo low-confidence words flagged.")
    with open("ocr_output_v2.txt", "w", encoding="utf-8") as f:
        f.write(text)
    print("\nSaved to ocr_output_v2.txt")

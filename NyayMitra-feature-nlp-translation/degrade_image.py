import sys
import cv2
import numpy as np

def degrade(image_path, output_path):
    img = cv2.imread(image_path)
    h, w = img.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, 4, 1.0)
    img = cv2.warpAffine(img, M, (w, h), borderValue=(255, 255, 255))
    small = cv2.resize(img, (w // 3, h // 3), interpolation=cv2.INTER_LINEAR)
    img = cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)
    img = cv2.GaussianBlur(img, (3, 3), 0)
    noise = np.random.normal(0, 12, img.shape).astype(np.int16)
    noisy = img.astype(np.int16) + noise
    img = np.clip(noisy, 0, 255).astype(np.uint8)
    img = cv2.convertScaleAbs(img, alpha=0.75, beta=40)
    cv2.imwrite(output_path, img)
    print(f"Degraded image saved to {output_path}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python degrade_image.py <input_image> <output_image>")
        sys.exit(1)
    degrade(sys.argv[1], sys.argv[2])

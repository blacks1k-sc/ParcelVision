import cv2
import numpy as np
from ocr_utils import extract_parcel_info


def detect_parcel_type(image_path):
    """
    Detects parcel type (Brown Box, White Package, Pink Package)
    based on dominant color while ignoring white label regions.
    """
    img = cv2.imread(image_path)
    img = cv2.resize(img, (600, 600))
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    # Mask out bright white label areas
    lower_white = np.array([0, 0, 200])
    upper_white = np.array([180, 60, 255])
    label_mask = cv2.inRange(hsv, lower_white, upper_white)
    background = cv2.bitwise_and(hsv, hsv, mask=cv2.bitwise_not(label_mask))

    # Compute average color for non-white regions
    nonzero = background[np.where(label_mask == 0)]
    avg = np.mean(nonzero, axis=0) if len(nonzero) > 0 else [0, 0, 0]
    h, s, v = avg

    if 10 < h < 30 and s > 40:
        return "BROWN BOX"
    elif v > 200 and s < 40:
        return "WHITE PACKAGE"
    elif h > 140:
        return "PINK PACKAGE"
    else:
        return "BOX"


def analyze_parcel(image_path):
    """
    Combines OCR (text extraction) and color-based parcel type detection.
    Returns a unified dictionary ready for Google Sheets logging.
    """
    info = extract_parcel_info(image_path)   # 🧠 Extracts unit, name, supplier
    parcel_type = detect_parcel_type(image_path)
    info["parcel_type"] = parcel_type
    return info
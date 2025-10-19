import cv2
import pytesseract
import re

def extract_parcel_info(image_path):
    img = cv2.imread(image_path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.bilateralFilter(gray, 9, 75, 75)
    _, thresh = cv2.threshold(gray, 0, 255,
                              cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # --- OCR ---
    text = pytesseract.image_to_string(thresh).upper()

    # --- Pattern-based parsing ---
    supplier = None
    for brand in ["AMAZON", "DHL", "FEDEX", "UPS", "UNI", "INTELCOM", "CANPAR"]:
        if brand in text:
            supplier = brand
            break

    unit = None
    unit_match = re.search(r"UNIT\s*(\d{1,5})", text)
    if unit_match:
        unit = unit_match.group(1)
    else:
        # many labels show the unit at line end, e.g. "GROVE 701"
        alt = re.search(r"\s(\d{3,5})(?:\s|$)", text)
        if alt:
            unit = alt.group(1)

    name_match = re.search(r"DELIVER TO.*?([A-Z\s]+)", text)
    name = name_match.group(1).strip() if name_match else None

    print("RETURNING OCR INFO TYPE:", type({
    "unit": unit or "UNKNOWN",
    "name": name or "UNKNOWN",
    "supplier": supplier or "UNKNOWN"
    }))

    return {
        "unit": unit or "UNKNOWN",
        "name": name or "UNKNOWN",
        "supplier": supplier or "UNKNOWN"
    }
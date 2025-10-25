"""
Parcel label extraction using Google Gemini Vision API.
Improved version for accurate unit (end-of-address) and supplier (FleetOptics) extraction.
"""

import os
import base64
import requests
import json
import re
from typing import Dict


def extract_with_gemini(image_path: str) -> Dict:
    """
    Uses Google Gemini to extract parcel information.
    Enhanced: removes letter prefixes from alphanumeric units (e.g., B308 → 308).
    """
    import cv2, pytesseract

    def run_ocr_fallback(img_path: str) -> str:
        img = cv2.imread(img_path)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.bilateralFilter(gray, 9, 75, 75)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return pytesseract.image_to_string(thresh).upper()

    def normalize_unit(u: str) -> str:
        """Remove prefixes like A308→308 but keep special words (PH, BSMT)."""
        if not u or u == "UNKNOWN":
            return "UNKNOWN"
        u = u.strip().upper()
        if re.fullmatch(r"[A-Z]\d{2,4}", u):  # B308 → 308
            u = re.sub(r"^[A-Z]", "", u)
        elif re.fullmatch(r"PH\d{1,3}", u):   # keep PH05 as 05
            u = re.sub(r"^PH", "", u)
        elif re.fullmatch(r"BSMT|BASEMENT|LOWER|UPPER|MAIN|G", u):
            return u
        return u

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("❌ GEMINI_API_KEY not found!")

    with open(image_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode()

    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash-lite:generateContent?key={api_key}"

    payload = {
        "contents": [{
            "parts": [
                {
                    "text": """Extract this shipping label as JSON only.

1. unit:
   - Apartment/suite/unit number. May be alphanumeric (e.g., B308, PH05, 4B).
   - If it contains a letter prefix (e.g., B308), return digits only → "308".
   - Ignore postal codes (M6H 0E5), tracking numbers, barcodes.

2. name: Full recipient name.

3. supplier: Amazon, UPS, FedEx, DHL, Purolator, Intelcom, FleetOptics, Canpar, Canada Post, or UNKNOWN.

4. parcel_type: BROWN BOX / WHITE PACKAGE / ENVELOPE.

Return JSON only:
{"unit":"308","name":"Keon Woong Chu","supplier":"AMAZON","parcel_type":"WHITE PACKAGE"}"""
                },
                {"inline_data": {"mime_type": "image/jpeg", "data": image_data}}
            ]
        }],
        "generationConfig": {"temperature": 0, "topP": 1, "maxOutputTokens": 4096}
    }

    print("🤖 Sending image to Gemini Vision API...")

    try:
        r = requests.post(url, json=payload, timeout=30)
        if r.status_code != 200:
            raise Exception(f"Gemini error {r.status_code}: {r.text}")

        result = r.json()
        text = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        text_clean = re.sub(r'```json\s*|\s*```', '', text).strip()

        json_match = re.search(r"\{[^{}]*\}", text_clean, re.DOTALL)
        data = json.loads(json_match.group(0)) if json_match else {}

        # Ensure keys exist
        for k in ["unit", "name", "supplier", "parcel_type"]:
            if k not in data or data[k] is None:
                data[k] = "UNKNOWN"

        # Supplier correction
        txt_up = text_clean.upper()
        if "AMAZON" in txt_up:
            data["supplier"] = "AMAZON"
        elif "UPS" in txt_up:
            data["supplier"] = "UPS"
        elif "FLEETOPTICS" in txt_up:
            data["supplier"] = "FLEETOPTICS"

        # OCR fallback for missing unit
        unit = str(data.get("unit") or "").strip().upper()
        if unit in ["", "UNKNOWN", "NONE"]:
            ocr_text = run_ocr_fallback(image_path)
            combined = (text_clean + "\n" + ocr_text).upper()
            patterns = [
                r"(?:UNIT|SUITE|APT|#)\s*([A-Z0-9\-]{1,6})",
                r"\b([A-Z]\d{2,4})\b",      # B308, A1205
                r"\b(\d{1,4}[A-Z])\b",      # 4B
                r"(?:GROVE|ROAD|STREET|DR|AVE|LANE|BLVD)\s+([A-Z0-9]{1,5})\b"
            ]
            match = None
            for p in patterns:
                match = re.search(p, combined)
                if match:
                    break
            data["unit"] = match.group(1) if match else "UNKNOWN"

        # Final normalization (strip prefixes)
        data["unit"] = normalize_unit(data.get("unit", "UNKNOWN"))
        for k in data:
            val = str(data[k]) if data[k] else ""
            data[k] = val.strip().upper() if val.strip() else "UNKNOWN"

        return data

    except Exception as e:
        print(f"\n❌ ERROR: {e}\n")
        return {
            "unit": "UNKNOWN",
            "name": "UNKNOWN",
            "supplier": "UNKNOWN",
            "parcel_type": "BROWN BOX"
        }

def extract_data(image_path: str) -> Dict:
    """
    Main entry point for parcel data extraction.
    """
    print(f"\n{'='*60}")
    print(f"🔍 ANALYZING: {os.path.basename(image_path)}")
    print(f"{'='*60}\n")

    try:
        result = extract_with_gemini(image_path)
        result = {
            "unit": str(result.get("unit", "UNKNOWN")).strip().upper(),
            "name": str(result.get("name", "UNKNOWN")).strip(),
            "supplier": str(result.get("supplier", "UNKNOWN")).strip().upper(),
            "parcel_type": str(result.get("parcel_type", "BROWN BOX")).strip().upper()
        }

        print(f"{'='*60}")
        print("✅ EXTRACTION SUCCESSFUL")
        print(f"{'='*60}")
        print(f"  📍 Unit:        {result['unit']}")
        print(f"  👤 Name:        {result['name']}")
        print(f"  🚚 Supplier:    {result['supplier']}")
        print(f"  📦 Type:        {result['parcel_type']}")
        print(f"{'='*60}\n")

        return result

    except Exception as e:
        print(f"\n❌ ERROR: {e}\n")
        return {
            "unit": "UNKNOWN",
            "name": "UNKNOWN",
            "supplier": "UNKNOWN",
            "parcel_type": "BROWN BOX"
        }


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python ocr_utils.py <image_path>")
        sys.exit(1)
    image_path = sys.argv[1]
    if not os.path.exists(image_path):
        print(f"❌ File not found: {image_path}")
        sys.exit(1)
    result = extract_data(image_path)
    print(f"\n📋 JSON OUTPUT:")
    print(json.dumps(result, indent=2))
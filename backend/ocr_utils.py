"""
Parcel label extraction using Google Gemini Vision API + local OCR/color fallback.
Final version – accurate unit (numeric only), name, supplier, and parcel_type detection.
Prioritizes local suppliers: Amazon, UPS, FedEx, UNI, Dragonfly, Emile, FleetOptics.
"""

import os
import base64
import requests
import json
import re
from typing import Dict
import cv2
import numpy as np
import pytesseract


# ----------------------------------------------------------------------
# --- FALLBACK HELPERS -------------------------------------------------
# ----------------------------------------------------------------------

def guess_parcel_type(image_path: str) -> str:
    """
    Simple color + texture classifier for parcel type.
    Determines parcel color and whether it's a box or package.
    """
    img = cv2.imread(image_path)
    if img is None:
        return "BROWN BOX"

    avg_color = cv2.mean(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))[:3]
    r, g, b = avg_color

    # Color detection
    if max(r, g, b) < 60:
        color = "BLACK"
    elif r > 200 and g > 200 and b > 200:
        color = "WHITE"
    elif r > 200 and g > 180 and b < 130:
        color = "YELLOW"
    elif abs(r - g) < 15 and abs(g - b) < 15:
        color = "GREY"
    else:
        color = "BROWN"

    # Edge density heuristic (rigid vs flexible)
    edges = cv2.Canny(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), 100, 200)
    edge_density = np.sum(edges > 0) / edges.size
    pkg_type = "BOX" if edge_density > 0.08 else "PACKAGE"

    return f"{color} {pkg_type}".upper()


def fallback_regex_ocr(image_path: str) -> Dict:
    """
    Backup OCR extraction using pytesseract + regex if Gemini fails.
    """
    text = pytesseract.image_to_string(image_path).upper()

    # --- Supplier detection ---
    suppliers_priority = [
        "AMAZON", "UPS", "FEDEX", "UNI", "DRAGONFLY", "EMILE", "FLEETOPTICS",
        "DHL", "PUROLATOR", "INTELCOM", "CANPAR", "CANADA POST"
    ]
    supplier = next((s for s in suppliers_priority if s in text), "OTHER")

    # --- Name detection ---
    name_match = re.search(r"([A-Z][A-Z'\-]+(?:\s+[A-Z][A-Z'\-]+)+)", text)
    name = name_match.group(1).title() if name_match else "UNKNOWN"

    # --- Unit detection (digits only) ---
    unit_match = re.search(r"(?:UNIT|SUITE|APT|#)?\s*-?\s*(\d{2,5})\b", text)
    unit = unit_match.group(1) if unit_match else "UNKNOWN"

    return {
        "unit": unit,
        "name": name,
        "supplier": supplier,
        "parcel_type": guess_parcel_type(image_path)
    }


# ----------------------------------------------------------------------
# --- GEMINI EXTRACTION ------------------------------------------------
# ----------------------------------------------------------------------

def extract_with_gemini(image_path: str) -> Dict:
    """
    Primary extraction via Gemini Vision API.
    Normalizes unit (digits only) and cross-checks supplier list.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError(
            "❌ GEMINI_API_KEY not found!\n"
            "Set it with: export GEMINI_API_KEY='your-key-here'"
        )

    with open(image_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode()

    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash-lite:generateContent?key={api_key}"

    prompt = """Extract the following fields from this shipping label and return ONLY JSON:
1. "unit": apartment/suite/unit number (digits only, e.g., 1911B → 1911, B-310 → 310)
2. "name": recipient's full name
3. "supplier": courier company — must be one of:
   AMAZON, UPS, FEDEX, UNI, DRAGONFLY, EMILE, FLEETOPTICS,
   DHL, PUROLATOR, INTELCOM, CANPAR, CANADA POST, or OTHER
4. "parcel_type": color + type (BROWN BOX, WHITE PACKAGE, GREY PACKAGE, etc.)

Return JSON only, no text explanation."""

    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": "image/jpeg", "data": image_data}}
            ]
        }],
        "generationConfig": {"temperature": 0, "topP": 1, "topK": 1, "maxOutputTokens": 4096}
    }

    print("🤖 Sending image to Gemini Vision API...")
    response = requests.post(url, json=payload, timeout=30)

    if response.status_code != 200:
        raise Exception(f"Gemini API error {response.status_code}: {response.text}")

    result = response.json()
    if not result.get("candidates"):
        raise Exception("No candidates in Gemini response")

    content = result["candidates"][0]["content"]["parts"][0].get("text", "").strip()
    content = re.sub(r'```json\s*|\s*```', '', content)
    json_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
    if not json_match:
        raise Exception(f"No valid JSON found in Gemini output:\n{content}")

    data = json.loads(json_match.group(0))

    # --- Normalize values ---
    unit_raw = str(data.get("unit", "")).upper().strip()
    digits = re.findall(r"\d{2,5}", unit_raw)
    data["unit"] = digits[0] if digits else "UNKNOWN"

    data["name"] = str(data.get("name", "UNKNOWN")).strip().title()

    supplier = str(data.get("supplier", "OTHER")).upper()
    valid_suppliers = {
        "AMAZON", "UPS", "FEDEX", "UNI", "DRAGONFLY", "EMILE", "FLEETOPTICS",
        "DHL", "PUROLATOR", "INTELCOM", "CANPAR", "CANADA POST"
    }
    if supplier not in valid_suppliers:
        supplier = "OTHER"
    data["supplier"] = supplier

    data["parcel_type"] = str(data.get("parcel_type", "BROWN BOX")).upper()

    return data


# ----------------------------------------------------------------------
# --- MAIN WRAPPER -----------------------------------------------------
# ----------------------------------------------------------------------

def extract_data(image_path: str) -> Dict:
    """
    Unified interface: Gemini first → fallback OCR + color if needed.
    """
    print(f"\n{'='*60}")
    print(f"🔍 ANALYZING: {os.path.basename(image_path)}")
    print(f"{'='*60}\n")

    try:
        result = extract_with_gemini(image_path)
    except Exception as e:
        print(f"⚠️ Gemini failed: {e}\nUsing fallback OCR...")
        result = fallback_regex_ocr(image_path)

    # Ensure all fields present or fallback-filled
    for key in ["unit", "name", "supplier", "parcel_type"]:
        if key not in result or not result[key] or result[key] == "UNKNOWN":
            print(f"⚠️ Missing {key}, re-filling via fallback...")
            backup = fallback_regex_ocr(image_path)
            if backup.get(key) and backup[key] != "UNKNOWN":
                result[key] = backup[key]

    print(f"{'='*60}")
    print("✅ FINAL EXTRACTION RESULT")
    print(f"{'='*60}")
    print(f"  📍 Unit:        {result['unit']}")
    print(f"  👤 Name:        {result['name']}")
    print(f"  🚚 Supplier:    {result['supplier']}")
    print(f"  📦 Type:        {result['parcel_type']}")
    print(f"{'='*60}\n")

    return result


# ----------------------------------------------------------------------
# --- CLI ENTRY --------------------------------------------------------
# ----------------------------------------------------------------------

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
    print("\n📋 JSON OUTPUT:")
    print(json.dumps(result, indent=2))
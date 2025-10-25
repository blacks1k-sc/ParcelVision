"""
Parcel label extraction using Google Gemini Vision API.
Fixed version with accurate unit extraction (preserves formats like B-310, A-2401).
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
    Preserves unit formats like B-310, A-2401, 604, etc.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    
    if not api_key:
        raise ValueError(
            "❌ GEMINI_API_KEY not found!\n"
            "Set it with: export GEMINI_API_KEY='your-key-here'\n"
            "Get a key at: https://makersuite.google.com/app/apikey"
        )
    
    # Read and encode image
    with open(image_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode()
    
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash-lite:generateContent?key={api_key}"
    
    payload = {
        "contents": [{
            "parts": [
                {
                    "text": """Extract from this shipping label as JSON:

1. unit: The apartment/suite/unit number. Look CAREFULLY:
   
   PATTERN 1 - Separate line before address:
   - "SUITE 604", "UNIT 2121", "APT 409", "#308"
   - "B-310", "A-2401", "PH-05"
   
   PATTERN 2 - Embedded in address (MOST COMMON):
   - "Aiman Javed 2002" → unit is 2002 (number after name)
   - "John Smith 604" → unit is 604
   - "308 - 185 Millway" → unit is 308 (before the dash)
   - "Jane Doe Apt 1205" → unit is 1205
   
   PATTERN 3 - Handwritten number (usually near top)
   
   CRITICAL RULES:
   - Unit is typically 2-4 digits: 604, 2002, 1205, etc.
   - If name is followed by a number, that number is the UNIT
   - DO NOT use street numbers: "185 Millway" → 185 is NOT the unit
   - DO NOT use postal codes: "M6H 0E5" is NOT the unit
   - If no clear unit found after checking all patterns → "UNKNOWN"

2. name: Recipient's full name
   - Usually first line after company header
   - Example: "Aiman Javed", "Shannon Edling", "Keon Woong Chu"

3. supplier: Courier company - check label carefully:
   - AMAZON (if "Amazon.com" visible)
   - UPS (UPS logo/text)
   - FEDEX (FedEx logo/text)
   - CANADA POST (if "CADC", "POSTE", "POSTES", or Canada Post visible)
   - DHL, PUROLATOR, INTELCOM, CANPAR, FLEETOPTICS
   - If no courier identified → "OTHER" (NOT "UNKNOWN")

4. parcel_type: COLOR + TYPE format:
   - Colors: BROWN, GREY, PINK, TRANSPARENT, BLACK, WHITE, YELLOW
   - Types: BOX (rigid) or PACKAGE (soft/flexible)
   - Examples: "BROWN BOX", "GREY PACKAGE", "PINK PACKAGE"

Return JSON only:
{"unit":"2002","name":"Aiman Javed","supplier":"CANADA POST","parcel_type":"BROWN PACKAGE"}
{"unit":"604","name":"Shannon Edling","supplier":"AMAZON","parcel_type":"WHITE PACKAGE"}
{"unit":"B-310","name":"John Smith","supplier":"OTHER","parcel_type":"BROWN BOX"}"""
                },
                {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": image_data
                    }
                }
            ]
        }],
        "generationConfig": {
            "temperature": 0,
            "topP": 1,
            "topK": 1,
            "maxOutputTokens": 8192
        }
    }
    
    print("🤖 Sending image to Gemini Vision API...")
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        
        if response.status_code != 200:
            error_data = response.json()
            error_msg = error_data.get("error", {}).get("message", response.text)
            raise Exception(f"Gemini API Error ({response.status_code}): {error_msg}")
        
        result = response.json()
        
        # Extract the text response
        if "candidates" not in result or not result["candidates"]:
            raise Exception("No response from Gemini API")
        
        candidate = result["candidates"][0]
        
        # Get the text content
        content = ""
        if "content" in candidate and "parts" in candidate["content"]:
            parts = candidate["content"]["parts"]
            if parts and "text" in parts[0]:
                content = parts[0]["text"]
        
        # If content is empty, the response was likely truncated
        if not content or candidate.get("finishReason") == "MAX_TOKENS":
            if "content" in candidate and "parts" in candidate["content"]:
                parts = candidate["content"]["parts"]
                if parts:
                    content = parts[0].get("text", "")
            
            if not content:
                raise Exception(f"Response truncated or empty. Candidate: {json.dumps(candidate, indent=2)}")
        
        if not content:
            raise Exception("No text in response")
        
        print(f"📝 Gemini response:\n{content}\n")
        
        # Clean up response - add closing brace if stopped
        content = content.strip()
        if not content.endswith("}"):
            content += "}"
        
        # Remove markdown if present
        content = re.sub(r'```json\s*|\s*```', '', content).strip()
        
        # Extract JSON object
        json_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
        if not json_match:
            raise Exception(f"No valid JSON found in: {content}")
        
        data = json.loads(json_match.group(0))
        
        # Validate and fill required keys
        required_keys = ["unit", "name", "supplier", "parcel_type"]
        for key in required_keys:
            if key not in data or not str(data[key]).strip():
                # Use "OTHER" for supplier if not found
                data[key] = "OTHER" if key == "supplier" else "UNKNOWN"
        
        # Replace "UNKNOWN" supplier with "OTHER"
        if str(data.get("supplier", "")).upper() in ["UNKNOWN", "NONE", ""]:
            data["supplier"] = "OTHER"
        
        # Clean up unit - normalize format
        unit = str(data.get("unit", "UNKNOWN")).strip().upper()
        
        # Remove single letter prefixes from alphanumeric units
        # B308 → 308, A2401 → 2401, but keep PH05, BSMT, etc.
        if re.fullmatch(r"[A-Z]-?\d{2,4}", unit):  # B308, B-308, A2401
            unit = re.sub(r"^[A-Z]-?", "", unit)  # Remove letter and optional dash
        
        data["unit"] = unit if unit and unit != "NONE" else "UNKNOWN"
        
        return data
    
    except requests.exceptions.Timeout:
        raise Exception("⏱️ Gemini API timeout - please try again")
    except requests.exceptions.RequestException as e:
        raise Exception(f"🌐 Network error: {e}")
    except json.JSONDecodeError as e:
        raise Exception(f"📝 Failed to parse JSON: {e}\nContent: {content}")


def extract_data(image_path: str) -> Dict:
    """
    Main entry point for parcel data extraction.
    
    Args:
        image_path: Path to the parcel image
        
    Returns:
        Dict with keys: unit, name, supplier, parcel_type
    """
    print(f"\n{'='*60}")
    print(f"🔍 ANALYZING: {os.path.basename(image_path)}")
    print(f"{'='*60}\n")
    
    try:
        result = extract_with_gemini(image_path)
        
        # Clean and normalize data (preserve unit format)
        result = {
            "unit": str(result.get("unit", "UNKNOWN")).strip().upper(),
            "name": str(result.get("name", "UNKNOWN")).strip().upper(),
            "supplier": str(result.get("supplier", "UNKNOWN")).strip().upper(),
            "parcel_type": str(result.get("parcel_type", "BROWN BOX")).strip().upper().replace("ENVELOPE", "PACKAGE").replace("POLY BAG", "PACKAGE").replace("MAILER", "PACKAGE")
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
        # Return fallback values
        return {
            "unit": "UNKNOWN",
            "name": "UNKNOWN",
            "supplier": "UNKNOWN",
            "parcel_type": "BROWN BOX"
        }


# For testing directly
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python ocr_utils.py <image_path>")
        print("\nExample:")
        print("  python ocr_utils.py uploads/parcel.jpg")
        sys.exit(1)
    
    image_path = sys.argv[1]
    
    if not os.path.exists(image_path):
        print(f"❌ File not found: {image_path}")
        sys.exit(1)
    
    result = extract_data(image_path)
    print(f"\n📋 JSON OUTPUT:")
    print(json.dumps(result, indent=2))
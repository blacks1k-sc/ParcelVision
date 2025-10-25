"""
Parcel label extraction using Google Gemini Vision API.
Replace your backend/ocr_utils.py with this file.
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
    Requires GEMINI_API_KEY environment variable.
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
    
    # Use the lightweight model which uses fewer tokens
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash-lite:generateContent?key={api_key}"
    
    payload = {
        "contents": [{
            "parts": [
                {
                    "text": "JSON output only: unit, name, supplier, parcel_type from label"
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
        if "content" in candidate and "parts" in candidate["content"]:
            parts = candidate["content"]["parts"]
            if parts and "text" in parts[0]:
                content = parts[0]["text"]
            else:
                raise Exception("No text in response parts")
        else:
            raise Exception(f"Unexpected response structure: {json.dumps(candidate, indent=2)}")
        
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
                data[key] = "UNKNOWN"
        
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
        
        # Clean and normalize data
        result = {
            "unit": str(result.get("unit", "UNKNOWN")).strip().upper(),
            "name": str(result.get("name", "UNKNOWN")).strip().upper(),
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
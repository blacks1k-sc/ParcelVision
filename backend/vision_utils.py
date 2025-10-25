"""
Vision utilities for parcel analysis.
Simply delegates to the Gemini-powered OCR.
"""

from ocr_utils import extract_data


def analyze_parcel(image_path):
    """
    Analyzes a parcel image and extracts label information.
    
    Args:
        image_path (str): Path to the parcel image
        
    Returns:
        dict: Contains unit, name, supplier, parcel_type
    """
    return extract_data(image_path)
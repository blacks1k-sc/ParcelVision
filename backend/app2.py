"""
app2.py - ParcelVision with Remote 1Valet Control (HTTPS Enabled)

Architecture:
- MacBook runs this Flask app (OCR + Google Sheets)
- Phone accesses MacBook via IP to scan parcels
- Work PC has 1Valet tab open with listener script
- MacBook sends unit data to Work PC browser via polling

Usage:
    python3 app2.py
    Access from phone: https://YOUR_MACBOOK_IP:5002 (Note: HTTPS)
"""

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import os
import sys
import inspect
import traceback
import json
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import local modules
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from vision_utils import analyze_parcel
from sheet_utils import append_row

print("🔍 Loaded modules:")
print(f"  - vision_utils from: {inspect.getfile(analyze_parcel)}")
print(f"  - sheet_utils from: {inspect.getfile(append_row)}")

# Setup Flask app
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = (
    os.path.join(BASE_DIR, "backend", "templates")
    if os.path.basename(BASE_DIR) != "backend"
    else os.path.join(BASE_DIR, "templates")
)

app = Flask(__name__, template_folder=TEMPLATE_DIR)
CORS(app)  # Enable CORS for cross-origin requests

UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Queue to store units pending 1Valet addition
pending_units_queue = []


# ============================================================
# ROUTES
# ============================================================

@app.route("/")
def home():
    """Serve the camera upload UI"""
    try:
        return render_template("index.html")
    except Exception as e:
        return f"<h3 style='color:red'>Template error: {e}</h3>", 500


@app.route("/upload", methods=["POST"])
def upload_parcel():
    """
    Complete workflow: OCR → Google Sheets → Queue for 1Valet
    """
    try:
        if "file" not in request.files:
            return jsonify({"error": "No file part"}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "No selected file"}), 400

        # Save temp file
        temp_path = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(temp_path)

        print("\n" + "="*60)
        print("📸 STEP 1: EXTRACTING PARCEL DATA")
        print("="*60)
        
        # Extract data using OCR
        result = analyze_parcel(temp_path)
        
        if isinstance(result, list):
            result = result[0] if result else {}

        unit = str(result.get("unit", "UNKNOWN")).strip().upper()
        name = str(result.get("name", "UNKNOWN")).strip().upper()
        supplier = str(result.get("supplier", "OTHER")).strip().upper()
        parcel_type = str(result.get("parcel_type", "BROWN BOX")).strip().upper()
        
        print(f"  📍 Unit:        {unit}")
        print(f"  👤 Name:        {name}")
        print(f"  🚚 Supplier:    {supplier}")
        print(f"  📦 Type:        {parcel_type}")

        # Step 2: Save to Google Sheets
        print("\n" + "="*60)
        print("📊 STEP 2: SAVING TO GOOGLE SHEETS")
        print("="*60)
        
        timestamp_readable = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
        timestamp_safe = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        row = [timestamp_readable, unit, name, supplier, parcel_type, "", ""]
        append_row(row)
        print("✅ Saved to Google Sheets")

        # Rename and save file
        safe_name = (
            f"{timestamp_safe}_{unit}_{name}_{supplier}_{parcel_type}.jpg"
        ).replace(" ", "_").replace("/", "-")
        final_path = os.path.join(UPLOAD_FOLDER, safe_name)
        os.rename(temp_path, final_path)

        # Step 3: Queue for 1Valet
        print("\n" + "="*60)
        print("🔐 STEP 3: QUEUEING FOR 1VALET")
        print("="*60)
        
        valet_status = "skipped"
        alert_message = None
        
        if unit == "UNKNOWN" or not unit or unit == "":
            # Alert for unknown unit
            valet_status = "error"
            alert_message = f"⚠️ UNIT NOT RECOGNIZED\nParcel for: {name}\nPlease add manually to 1Valet"
            print(f"❌ {alert_message}")
        else:
            # Add to queue for 1Valet browser listener
            pending_units_queue.append({
                "unit": unit,
                "name": name,
                "supplier": supplier,
                "parcel_type": parcel_type,
                "timestamp": timestamp_readable
            })
            valet_status = "queued"
            print(f"✓ Unit {unit} queued for 1Valet")
            print(f"✓ Queue size: {len(pending_units_queue)}")

        print("\n" + "="*60)
        print("✅ WORKFLOW COMPLETE")
        print("="*60)
        
        response_data = {
            "status": "success",
            "message": "Parcel processed successfully",
            "image_saved_as": safe_name,
            "data": {
                "unit": unit,
                "name": name,
                "supplier": supplier,
                "parcel_type": parcel_type
            },
            "sheets_status": "success",
            "valet_status": valet_status,
            "alert": alert_message
        }
        
        return jsonify(response_data), 200

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        traceback.print_exc()
        return jsonify({
            "error": str(e),
            "alert": f"⚠️ ERROR PROCESSING PARCEL\n{str(e)}"
        }), 500


@app.route("/valet/pending", methods=["GET"])
def get_pending_units():
    """
    API endpoint for 1Valet browser to poll for pending units.
    The browser script on Work PC calls this to get units to add.
    """
    global pending_units_queue
    
    if not pending_units_queue:
        return jsonify({
            "status": "empty",
            "units": []
        })
    
    # Return all pending units
    units = pending_units_queue.copy()
    
    return jsonify({
        "status": "pending",
        "count": len(units),
        "units": units
    })


@app.route("/valet/complete", methods=["POST"])
def mark_unit_complete():
    """
    Called by browser script after successfully adding unit to 1Valet.
    """
    global pending_units_queue
    
    data = request.get_json()
    unit = data.get("unit")
    success = data.get("success", False)
    
    if success:
        # Remove from queue
        pending_units_queue = [u for u in pending_units_queue if u["unit"] != unit]
        print(f"✅ Unit {unit} marked complete and removed from queue")
        print(f"   Remaining in queue: {len(pending_units_queue)}")
        
        return jsonify({
            "status": "success",
            "message": f"Unit {unit} removed from queue",
            "remaining": len(pending_units_queue)
        })
    else:
        print(f"⚠️ Unit {unit} failed to add to 1Valet")
        return jsonify({
            "status": "error",
            "message": "Failed to add unit"
        }), 400


@app.route("/valet/queue-status", methods=["GET"])
def queue_status():
    """Check status of pending units queue."""
    return jsonify({
        "queue_size": len(pending_units_queue),
        "pending_units": [u["unit"] for u in pending_units_queue]
    })


@app.route("/valet/clear-queue", methods=["POST"])
def clear_queue():
    """Clear all pending units (emergency reset)."""
    global pending_units_queue
    count = len(pending_units_queue)
    pending_units_queue = []
    
    return jsonify({
        "status": "success",
        "message": f"Cleared {count} units from queue"
    })


if __name__ == "__main__":
    print("\n" + "="*60)
    print("🚀 ParcelVision Enhanced - Remote 1Valet Control")
    print("="*60)
    print("\n📋 Architecture:")
    print("  1. MacBook runs this server")
    print("  2. Phone scans parcels via MacBook IP")
    print("  3. Data saved to Google Sheets")
    print("  4. Units queued for 1Valet")
    print("  5. Work PC browser polls this server")
    print("  6. Browser auto-adds units to 1Valet")
    
    print("\n📱 Access from phone:")
    print("  https://YOUR_MACBOOK_IP:5002  <-- NOTE: HTTPS")
    
    print("\n💻 Work PC Setup:")
    print("  1. Open 1Valet SmartLockers tab")
    print("  2. Open Console (F12)")
    print("  3. Paste listener script (see valet_listener.js)")
    
    print("\n⚙️  Endpoints:")
    print("  GET  /valet/pending       - Get units to add")
    print("  POST /valet/complete      - Mark unit added")
    print("  GET  /valet/queue-status  - Check queue")
    print("  POST /valet/clear-queue   - Clear all")
    
    # --- START SSL (HTTPS) CONFIGURATION ---
    print("\n" + "="*60)
    print("🔒 CONFIGURING HTTPS (SSL)")
    
    # Automatically find the user's home directory
    home_dir = os.path.expanduser("~")
    cert_path = os.path.join(home_dir, "ssl-certs", "cert.pem")
    key_path = os.path.join(home_dir, "ssl-certs", "key.pem")

    # Check if the certificate and key files exist
    if not os.path.exists(cert_path) or not os.path.exists(key_path):
        print(f"❌ ERROR: SSL certs not found.")
        print(f"  Expected cert at: {cert_path}")
        print(f"  Expected key at:  {key_path}")
        print("\n💡 Please run the 'openssl' command from the previous step")
        print("   to generate these files in your '~/ssl-certs' folder.")
        sys.exit(1) # Exit if certs are missing
    
    print(f"✓ Found certificate: {cert_path}")
    print(f"✓ Found private key: {key_path}")
    
    ssl_context = (cert_path, key_path)
    # --- END SSL (HTTPS) CONFIGURATION ---
    
    print("\n" + "="*60)
    print("🌐 Server starting on https://0.0.0.0:5002  <-- HTTPS")
    print("="*60 + "\n")
    
    # Get MacBook IP for easy reference
    try:
        import socket
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        print(f"💡 Your MacBook IP: {local_ip}")
        print(f"   Access from phone: https://{local_ip}:5002\n") # <-- HTTPS
        print("⚠️ REMINDER: Your phone and Work PC must TRUST this new certificate!")
    except Exception as e:
        print("Could not determine local IP. Please find it in System Settings > Network.")
        print(f"   Access from phone: https://YOUR_MAC_IP:5002\n")
    
    # Run the app with the SSL context
    app.run(host="0.0.0.0", port=5002, debug=True, ssl_context=ssl_context)
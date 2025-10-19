import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# 🔐 Connect to Google Sheets
def connect_to_sheet():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
    client = gspread.authorize(creds)

    sheet_id = "1kk26zI931UdarkoIgLES08YF4X2w5Y45-43_4aQD3bQ"
    worksheet_name = "PACKAGES NEW"
    sheet = client.open_by_key(sheet_id).worksheet(worksheet_name)
    return sheet  # ✅ Only the worksheet object, not a tuple


# ✅ Append a parcel entry inside the filtered table boundary
def append_row(data):
    sheet = connect_to_sheet()
    timestamp = datetime.now().strftime("%m/%d/%Y %H:%M:%S")

    row = [
        timestamp,                      # Column A (Timestamp)
        data.get("unit", ""),            # Column B (UNIT)
        data.get("name", ""),            # Column C (NAME)
        data.get("supplier", ""),        # Column D (PACKAGE COMPANY)
        data.get("parcel_type", ""),     # Column E (PARCEL TYPE)
        "",                              # Column F (RELEASED ?)
        ""                               # Column G (RELEASED TIME)
    ]

    # Find last filled visible row in Column A
    col_a = sheet.col_values(1)
    last_filled_row = len(col_a)
    if last_filled_row == 0:
        last_filled_row = 1

    next_row = last_filled_row + 1
    sheet.insert_row(row, index=next_row, value_input_option="USER_ENTERED")

    print(f"✅ Added new parcel entry inside filtered range at row {next_row}")
    return row


# 🧩 Get the last visible parcel entry
def get_last_entry():
    sheet = connect_to_sheet()
    values = sheet.get_all_values()
    if not values or len(values) <= 1:
        return None
    headers = values[0]
    last_row = values[-1]
    return dict(zip(headers, last_row))
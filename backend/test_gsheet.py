import gspread
from oauth2client.service_account import ServiceAccountCredentials

def test_google_sheet_connection():
    # define the scopes
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]

    # load credentials
    creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
    client = gspread.authorize(creds)

    # open the sheet using its unique ID (from the URL)
    sheet = client.open_by_key("1kk26zI931UdarkoIgLES08YF4X2w5Y45-43_4aQD3bQ").sheet1

    # add a test row (won’t overwrite anything)
    sheet.append_row(["✅ TEST ENTRY", "404", "ANGELA", "AMAZON", "BROWN BOX", "", ""])

    print("✅ Successfully connected and added a test row to your Google Sheet!")

if __name__ == "__main__":
    test_google_sheet_connection()
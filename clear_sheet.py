"""
Clear all data rows (keep header) from the Grant Screening sheet.
Run: python clear_sheet.py
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8")
from dotenv import load_dotenv
load_dotenv()

import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
gc = gspread.authorize(creds)

sh = gc.open_by_key(os.getenv("GOOGLE_SHEET_ID"))
ws = sh.worksheet("Grant Screening")

all_vals = ws.get_all_values()
if all_vals:
    ws.clear()

    # Reset all background colors
    sh.batch_update({"requests": [{
        "repeatCell": {
            "range": {
                "sheetId": ws.id,
                "startRowIndex": 0,
                "endRowIndex": 1000,
                "startColumnIndex": 0,
                "endColumnIndex": 26,
            },
            "cell": {"userEnteredFormat": {"backgroundColor": {"red": 1, "green": 1, "blue": 1}}},
            "fields": "userEnteredFormat.backgroundColor",
        }
    }]})

    print(f"Cleared {len(all_vals)} row(s) and all colors.")
else:
    print("Sheet is already empty.")

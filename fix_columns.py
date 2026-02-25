"""
fix_columns.py
Deletes the old 'Amount' column (col E, index 4) from the existing sheet
so Sources shifts left into the correct position, without clearing any rows.
Run once: python fix_columns.py
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

# Check current header row
headers = ws.row_values(1)
print(f"Current headers: {headers}")

if "Amount" not in headers:
    print("Amount column not found — nothing to fix.")
else:
    amount_col = headers.index("Amount")  # 0-based
    print(f"Deleting 'Amount' column at index {amount_col} (column {amount_col + 1})...")

    sh.batch_update({"requests": [{
        "deleteDimension": {
            "range": {
                "sheetId": ws.id,
                "dimension": "COLUMNS",
                "startIndex": amount_col,      # 0-based, inclusive
                "endIndex": amount_col + 1,    # exclusive
            }
        }
    }]})

    print("Done! New headers:", ws.row_values(1))

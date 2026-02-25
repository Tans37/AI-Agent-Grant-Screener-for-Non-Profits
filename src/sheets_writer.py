"""
Google Sheets Writer
Writes grant screening results live to a Google Spreadsheet as each grant
is processed, using a Service Account for authentication.

Setup (one-time):
  1. Go to https://console.cloud.google.com/
  2. Create a project -> Enable "Google Sheets API" and "Google Drive API"
  3. Create a Service Account -> download the JSON key as credentials.json
  4. Place credentials.json in the project root
  5. Share your Google Sheet with the service account email (Editor access)
  6. Add GOOGLE_SHEET_ID=<your_sheet_id> to .env
     (Sheet ID is in the URL: docs.google.com/spreadsheets/d/<SHEET_ID>/edit)
"""

import os
import gspread
from google.oauth2.service_account import Credentials
from .models import ScreeningResult

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

HEADERS = [
    "Foundation",
    "Classification",
    "Confidence",
    "Rationale",
    "Sources",
]


# Plain-text labels (no emoji) to avoid Windows cp1252 encoding errors
CLASS_LABEL = {
    "GREEN":  "GREEN",
    "YELLOW": "YELLOW",
    "RED":    "RED",
}


class SheetsWriter:
    def __init__(self, sheet_id: str | None = None, credentials_path: str = "credentials.json"):
        sheet_id = sheet_id or os.getenv("GOOGLE_SHEET_ID")
        if not sheet_id:
            raise ValueError("GOOGLE_SHEET_ID not set in .env or passed as argument.")
        if not os.path.exists(credentials_path):
            raise FileNotFoundError(
                f"credentials.json not found at '{credentials_path}'. "
                "Download it from Google Cloud Console (Service Account -> Keys)."
            )

        creds = Credentials.from_service_account_file(credentials_path, scopes=SCOPES)
        self.gc = gspread.authorize(creds)

        self.sheet = self.gc.open_by_key(sheet_id)
        self.ws = self._get_or_create_worksheet("Grant Screening")

    # ── Worksheet setup ──────────────────────────────────────────────────────

    def _get_or_create_worksheet(self, title: str) -> gspread.Worksheet:
        """Return existing worksheet or create a fresh one with headers."""
        try:
            ws = self.sheet.worksheet(title)
        except gspread.WorksheetNotFound:
            ws = self.sheet.add_worksheet(title=title, rows=500, cols=len(HEADERS))

        # Write headers if the sheet is empty
        if ws.row_count == 0 or not ws.row_values(1):
            ws.append_row(HEADERS, value_input_option="USER_ENTERED")

        return ws

    def ensure_headers(self):
        """Write headers only if row 1 is empty (never overwrite existing headers)."""
        first_row = self.ws.row_values(1) if self.ws.row_count > 0 else []
        if not first_row:
            self.ws.insert_row(HEADERS, 1, value_input_option="USER_ENTERED")

    # ── Writing results ──────────────────────────────────────────────────────

    def get_processed_foundations(self) -> set[str]:
        """Return a set of foundation names already recorded in the sheet."""
        try:
            all_values = self.ws.get_all_values()
            # Skip header row, grab column 0 (Foundation)
            return {row[0].strip() for row in all_values[1:] if row and row[0].strip()}
        except Exception as e:
            print(f"[Sheets] Could not read processed foundations: {e}")
            return set()

    # Row background colors per classification (light pastel shades)
    ROW_COLORS = {
        "GREEN":  {"red": 0.714, "green": 0.843, "blue": 0.659},   # light green
        "YELLOW": {"red": 1.0,   "green": 0.949, "blue": 0.8},     # light yellow
        "RED":    {"red": 0.918, "green": 0.600, "blue": 0.600},   # light red
    }

    def append_result(self, result: ScreeningResult):
        """Append a single screening result as a new row (live update) with color."""
        classification = CLASS_LABEL.get(result.classification.value, result.classification.value)
        urls = self._extract_urls(result.sources)

        # Strip "Red flags: ... Green flags: X/8 (...)." prefix for the sheet
        clean_rationale = self._clean_rationale(result.rationale)

        row = [
            result.grant.foundation_name,
            classification,
            result.confidence_score,
            clean_rationale,
            "",   # Sources placeholder — filled with rich text below
        ]
        self.ws.append_row(row, value_input_option="USER_ENTERED")

        # Get the row index we just wrote
        row_index = len(self.ws.get_all_values())  # 1-based

        # Write Sources cell as rich text with individual hyperlinks
        if urls:
            try:
                self._write_hyperlink_cell(row_index, col_index=len(HEADERS) - 1, urls=urls)
            except Exception as e:
                print(f"    [Sheets] hyperlink write failed: {e}")

        # Color the row
        color = self.ROW_COLORS.get(result.classification.value)
        if color:
            self._color_row(row_index, color)


    def _color_row(self, row_index: int, color: dict):
        """Apply a background color to all columns of the given row (1-based)."""
        sheet_id = self.ws.id
        requests = [{
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": row_index - 1,   # 0-based
                    "endRowIndex":   row_index,
                    "startColumnIndex": 0,
                    "endColumnIndex":   len(HEADERS),
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": color
                    }
                },
                "fields": "userEnteredFormat.backgroundColor",
            }
        }]
        self.sheet.batch_update({"requests": requests})

    @staticmethod
    def _clean_rationale(rationale: str) -> str:
        """
        Strip the structured flag prefix from the rationale so the sheet shows
        only the plain context sentence.

        Input:  "Red flags: None. Green flags: 5/8 (G1✓ G3✓). Akamai funds STEM..."
        Output: "Akamai funds STEM..."
        """
        import re
        # Remove "Red flags: .... Green flags: X/N (...)." at the start
        cleaned = re.sub(
            r"^Red flags:.*?Green flags:\s*\d+/\d+\s*\([^)]*\)\.\s*",
            "",
            rationale,
            flags=re.IGNORECASE | re.DOTALL,
        ).strip()
        return cleaned if cleaned else rationale   # fallback to original if regex fails

    def _write_hyperlink_cell(self, row_index: int, col_index: int, urls: list[str]):
        """
        Write multiple clickable hyperlinks into a single cell using the Sheets API
        rich text (textFormatRuns). Each URL becomes a separate line.
        """
        # Build the full cell string: "domain1\ndomain2\n..."
        labels = []
        for url in urls:
            label = url.replace("https://", "").replace("http://", "").split("/")[0]
            labels.append(label)
        full_text = "\n".join(labels)

        # Build textFormatRuns — one run per link
        runs = []
        char_pos = 0
        for label, url in zip(labels, urls):
            runs.append({
                "startIndex": char_pos,
                "format": {
                    "link": {"uri": url},
                    "foregroundColor": {"red": 0.067, "green": 0.396, "blue": 0.745},
                    "underline": True,
                }
            })
            char_pos += len(label) + 1  # +1 for the \n separator (except after last label)

        self.sheet.batch_update({"requests": [{
            "updateCells": {
                "rows": [{
                    "values": [{
                        "userEnteredValue": {"stringValue": full_text},
                        "textFormatRuns": runs,
                    }]
                }],
                "fields": "userEnteredValue,textFormatRuns",
                "range": {
                    "sheetId": self.ws.id,
                    "startRowIndex": row_index - 1,   # 0-based
                    "endRowIndex":   row_index,
                    "startColumnIndex": col_index,
                    "endColumnIndex":   col_index + 1,
                },
            }
        }]})

    def _build_hyperlink_cells(self, sources: list[str] | None) -> list:
        """(Unused — kept for reference) Return HYPERLINK formulas."""
        urls = self._extract_urls(sources)
        cells = []
        for i in range(5):
            if i < len(urls):
                url = urls[i]
                label = url.replace("https://", "").replace("http://", "").split("/")[0]
                cells.append(f'=HYPERLINK("{url}","{label}")')
            else:
                cells.append("")
        return cells


    def _extract_urls(self, sources: list[str] | None) -> list[str]:
        """Extract raw URLs from source strings, filtering out internal redirect URLs."""
        if not sources:
            return []
        SKIP_DOMAINS = ("vertexaisearch.cloud.google.com", "google.com/search")
        urls = []
        for s in sources:
            if "(" in s and s.endswith(")"):
                url = s[s.index("(") + 1:-1]
            else:
                url = s
            if url and url not in urls and not any(d in url for d in SKIP_DOMAINS):
                urls.append(url)
        return urls


    def clear_results(self):
        """Clear all rows below the header (fresh run)."""
        all_values = self.ws.get_all_values()
        if len(all_values) > 1:
            # Delete rows from row 2 downward
            self.ws.delete_rows(2, len(all_values))
        print("[Sheets] Cleared previous results.")

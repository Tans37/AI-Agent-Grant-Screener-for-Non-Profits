# AI Grant Screener

An automated grant screening pipeline that uses **Gemini AI + SerpAPI** to research, classify, and export grant opportunities to Google Sheets in real time.

## What it does

- Pulls grant opportunities from a MySQL/CRM database
- Searches **ProPublica**, **Granted**, **Candid**, and **CauseIQ** via SerpAPI for each foundation
- Uses **Gemini 3 Flash** with Google Search grounding to classify each grant as:
  - 🟢 **GREEN** — Strong match, apply
  - 🟡 **YELLOW** — Needs review or follow-up
  - 🔴 **RED** — Poor fit, skip
- Writes results live to **Google Sheets** with:
  - Color-coded rows
  - Clickable hyperlinks in the Sources column
  - Skip logic to avoid re-processing grants already in the sheet

## Classification Logic

The model follows a strict 3-step chain-of-thought:

1. **Check Red Flags (R1a–R8)** — hard disqualifiers (closed, wrong geography, wrong focus, etc.)
   - R1b exception: *invitation-only* foundations with ≥1 green flag → YELLOW (worth reaching out)
2. **Count Green Flags (G1–G8)** — positive alignment signals (STEM, NJ funding, youth, equity, etc.)
3. **Classify** — GREEN if ≥4 green flags, YELLOW if ≤3, RED if any hard flag triggered

## Project Structure

```
.
├── main.py                  # Entry point
├── clear_sheet.py           # Wipe all rows + colors from the sheet
├── count_backlog.py         # Count grants in the DB backlog
├── fix_columns.py           # One-time column layout migration utility
├── requirements.txt
├── .env.example             # Copy to .env and fill in your values
├── credentials.json.example # See Google Sheets setup below
└── src/
    ├── gemini_client.py     # Gemini + SerpAPI screening logic
    ├── serp_searcher.py     # SerpAPI priority source searches
    ├── sheets_writer.py     # Google Sheets writer (live, colored, hyperlinked)
    ├── db_connector.py      # MySQL connector
    └── models.py            # Grant / ScreeningResult data models
```

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure environment
```bash
cp .env.example .env
# Fill in all values in .env
```

### 3. Google Sheets (Service Account)
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project → Enable **Google Sheets API** and **Google Drive API**
3. Create a **Service Account** → download the JSON key as `credentials.json`
4. Share your Google Sheet with the service account email (Editor access)
5. Copy the Sheet ID from the URL into `.env` as `GOOGLE_SHEET_ID`

### 4. Run
```bash
python main.py        # Screen grants and write to Sheets
python clear_sheet.py # Clear all rows and colors from the sheet
python count_backlog.py  # Check how many grants are in the DB backlog
```

## API Keys Required

| Service | Where to get it |
|---|---|
| Gemini | [Google AI Studio](https://aistudio.google.com/app/apikey) |
| SerpAPI | [serpapi.com](https://serpapi.com/) |
| Google Sheets | Service Account JSON via Google Cloud Console |

## Configuration via .env

All org-specific settings are in `.env` — no org details are hardcoded:

```env
ORG_NAME=Your Nonprofit Name
ORG_MISSION=providing STEM education to underserved youth
ORG_STATE=NJ
ORG_TARGET_CITIES=Newark, Camden, Jersey City
DB_TABLE=YourSchema.Grant_Opportunities
DB_STAGE_FILTER=LOI Backlog
```

## Notes

- `credentials.json` and `.env` are excluded from git via `.gitignore` — never commit them
- The pipeline skips grants already present in the Google Sheet (by foundation name)
- Temperature is set to 0 for deterministic, consistent classifications

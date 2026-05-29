# AI Grant Screener for Non-Profits

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)
![Gemini](https://img.shields.io/badge/Gemini-3_Flash-orange?logo=google&logoColor=white)
![SerpAPI](https://img.shields.io/badge/SerpAPI-Search-green?logo=google-search&logoColor=white)
![Google Sheets](https://img.shields.io/badge/Google_Sheets-Live_Export-34A853?logo=googlesheets&logoColor=white)
![MySQL](https://img.shields.io/badge/MySQL-Database-4479A1?logo=mysql&logoColor=white)

An autonomous, AI-driven grant screening pipeline that researches, reasons, and classifies grant opportunities at scale. The system evaluates backlog opportunities against user-defined criteria, leveraging search grounding and structured chain-of-thought reasoning to provide actionable, deterministic classifications exported live to Google Sheets.

Designed for nonprofits managing large opportunity pipelines, this tool replaces manual due diligence with an automated, verifiable AI workflow.

---

## System Architecture

The pipeline operates in two distinct phases: **Configuration Generation** and **Execution & Screening**.

### 1. Configuration Generation (Meta-Prompting)
Instead of hardcoding rules, the system uses a **meta-prompting** architecture. 
The setup wizard (`setup_wizard.py`) collects plain-English organizational context, disqualifiers, and positive indicators. It then queries the Gemini API to compile these inputs into a structured JSON schema (`screener_config.json`). This schema defines the specific Boolean flags and thresholds the evaluation engine will use later.

### 2. Execution & Screening Pipeline (Hybrid Web RAG)
During the execution phase (`main.py`), the system processes grants through a multi-stage data retrieval and reasoning loop, functioning as a **Hybrid Web RAG** pipeline:

```text
[MySQL / CRM Database] 
      │ (Fetches unprocessed grant backlog)
      ▼
[Data Enrichment via SerpAPI]  <-- DETERMINISTIC WEB RAG
      │ Searches high-signal domains for 990s and grant history:
      │ ├─ ProPublica Nonprofit Explorer (site:projects.propublica.org)
      │ ├─ Granted AI (site:grantedai.com)
      │ ├─ Candid (site:candid.org)
      │ └─ CauseIQ (site:causeiq.com)
      ▼
[Reasoning Engine: Gemini 3 Flash]
      │ (Ingests pre-fetched context + screener_config.json)
      │ 
      │ ➔ Fallback Grounding: If SerpAPI data is insufficient, Gemini invokes 
      │    the native `google_search` tool to run live web queries. <-- AGENTIC WEB RAG
      │
      │ ➔ Chain-of-Thought Evaluation:
      │    1. Evaluates all Red Flags (Immediate disqualifiers)
      │    2. Evaluates all Green Flags (Positive signals)
      │    3. Applies logic thresholds (e.g., ≥4 Green Flags = GREEN)
      ▼
[Google Sheets Exporter]
      │ Writes structured results via Google Sheets API
      │ Applies conditional formatting (Color-coded rows)
      │ Injects rich-text hyperlinked citations
```

## Key Technical Features

- **Deterministic AI Execution**: The Gemini model runs with `temperature=0` to ensure highly reproducible evaluations.
- **Hybrid Web RAG Architecture**: Combines **Deterministic Web RAG** (pre-fetching tax data and programmatic structures via SerpAPI) with **Agentic Web RAG** (Gemini's native Google Search grounding for open-web fallback).
- **Robust Schema Enforcement**: Model outputs are strictly enforced to return a standardized JSON schema containing the classification, a chain-of-thought rationale, a confidence score, and citation links.
- **Stateful Processing**: The Google Sheets writer tracks previously processed grants, ensuring idempotency and safe re-runs against the database backlog.
- **Live Output Streaming**: Results are pushed to Google Sheets synchronously after each foundation is evaluated, rather than batching at the end, providing real-time observability.

---

## Project Structure

```text
.
├── setup_wizard.py      # Meta-prompting CLI: Generates screener_config.json via LLM
├── update_config.py     # Targeted config mutation utility for modifying specific flags
├── main.py              # Primary execution entrypoint
├── clear_sheet.py       # Google Sheets API utility to wipe data and formatting
├── count_backlog.py     # MySQL utility to inspect database row counts
├── fix_columns.py       # Google Sheets utility to realign schema columns
├── test_db_connection.py# Diagnostics script to verify DB connectivity and schema views
├── .env.example         # Environment variable template
├── requirements.txt     # Python dependencies
└── src/
    ├── gemini_client.py    # Gemini SDK integration, dynamic prompt compilation, and JSON parsing
    ├── serp_searcher.py    # SerpAPI wrapper with site-specific domain filtering logic
    ├── sheets_writer.py    # Google Sheets API integration and rich-text formatting
    ├── db_connector.py     # MySQL/CRM connection pool and query execution
    └── models.py           # Pydantic/Dataclass data models for Grants and Results
```

---

## Setup & Deployment

### 1. Prerequisites

- **Python 3.10+**
- **Database**: A MySQL-compatible database containing grant records.
- **API Credentials**:
  - [Google AI Studio API Key](https://aistudio.google.com/app/apikey) (for `google-genai` SDK)
  - [SerpAPI Key](https://serpapi.com/)
  - Google Cloud Service Account JSON (with Sheets & Drive API access)

### 2. Installation

```bash
git clone https://github.com/Tans37/AI-Agent-Grant-Screener-for-Non-Profits.git
cd AI-Agent-Grant-Screener-for-Non-Profits
pip install -r requirements.txt
```

### 3. Environment Configuration

Copy the template environment file:

```bash
cp .env.example .env
```

Configure the `.env` variables:

```env
# Database Configuration
MYSQL_HOST=db.example.com
MYSQL_USER=admin
MYSQL_PASSWORD=secure_password
MYSQL_DB=crm_database
MYSQL_PORT=3306

# Table Targeting
DB_TABLE=YourSchema.Grant_Opportunities
DB_STAGE_FILTER=Backlog

# API Keys
GEMINI_API_KEY=your_gemini_api_key
SERPAPI_KEY=your_serpapi_key

# Google Sheets Target
GOOGLE_SHEET_ID=your_google_sheet_id
```

### 4. Google Sheets Authentication

1. Generate a Service Account JSON key from the Google Cloud IAM Console.
2. Save it to the project root as `credentials.json`.
3. Share your target Google Sheet with the Service Account email (Editor permissions).

---

## Operation & Workflow

### Compiling the Ruleset (First Run)
Run the setup wizard to generate the evaluation ruleset. The AI will prompt you for your constraints and synthesize the Boolean flag logic.

```bash
python setup_wizard.py
```
*The resulting configuration is cached in `screener_config.json`.*

### Executing the Pipeline
Run the main evaluation loop. The script will open a database connection, fetch the backlog, initialize the Gemini client, and begin streaming results to Sheets.

```bash
python main.py
```

### Output Schema (Google Sheets)

| Field | Data Type | Description |
|---|---|---|
| **Foundation** | `String` | Entity name |
| **Classification** | `Enum` | `GREEN` (Strong Fit) / `YELLOW` (Review Required) / `RED` (Disqualified) |
| **Confidence** | `Float` | Model confidence score (0.0 - 1.0) |
| **Rationale** | `String` | Chain-of-thought summary identifying which flags triggered the classification. |
| **Sources (1-5)**| `URI` | Rich-text hyperlinks to source material discovered during grounding. |

---

## Configuration Management

You can mutate specific configuration blocks without regenerating the entire ruleset:

```bash
# Display the current JSON configuration
python update_config.py --show

# Mutate specific configuration trees
python update_config.py --org              # Update entity details
python update_config.py --rules            # Re-run LLM flag synthesis
python update_config.py --classification   # Modify Enum thresholds
python update_config.py --size             # Update grant capital constraints
python update_config.py --threshold        # Adjust Boolean flag threshold requirements
```

---

## Roadmap

- [ ] Support for alternative data sources (Airtable, PostgreSQL)
- [ ] Integration with orchestration tools (GitHub Actions, cron) for continuous screening
- [ ] Asynchronous parallel processing for high-volume grant evaluation
- [ ] Webhooks for Slack/Teams notifications upon high-confidence `GREEN` classifications

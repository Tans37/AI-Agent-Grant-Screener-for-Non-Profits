import os
from dotenv import load_dotenv
from src.db_connector import DBConnector
from src.gemini_client import GeminiClient
from src.models import Classification
from src.sheets_writer import SheetsWriter
from tabulate import tabulate

def main():
    load_dotenv()
    
    print("Initializing Grants Screening Pipeline...")
    
    # 1. Connect to DB and fetch backlog
    db = DBConnector()
    print("Fetching grants from backlog...")
    grants = db.fetch_backlog_grants(limit=50) 
    
    if not grants:
        print("No grants found in backlog.")
        return

    # 2. Initialize Gemini
    try:
        screener = GeminiClient()
    except ValueError as e:
        print(f"Configuration Error: {e}")
        return

    # 3. Initialize Google Sheets writer (optional — skips if not configured)
    sheets = None
    try:
        sheets = SheetsWriter()
        sheets.ensure_headers()
        print("[Sheets] Connected. Results will be written live to Google Sheets.")
    except (ValueError, FileNotFoundError) as e:
        print(f"[Sheets] Skipping live export: {e}")

    # 4. Skip already-processed grants
    if sheets:
        processed = sheets.get_processed_foundations()
        if processed:
            before = len(grants)
            grants = [g for g in grants if g.foundation_name.strip() not in processed]
            skipped = before - len(grants)
            print(f"[Sheets] Skipping {skipped} already-processed grant(s).")
    print()

    results = []

    # 4. Process each grant and push to Sheets live
    print(f"Screening {len(grants)} grants...\n")
    for i, grant in enumerate(grants, 1):
        print(f"[{i}/{len(grants)}] Processing: {grant.foundation_name}...")
        result = screener.screen_grant(grant)
        results.append(result)
        print(f"  -> {result.classification.value} (conf: {result.confidence_score})")

        # Push to Sheets immediately after each result
        if sheets:
            try:
                sheets.append_result(result)
                print(f"  -> Written to Sheets ✓")
            except Exception as e:
                print(f"  -> Sheets write failed: {e}")

    # 5. Console Report
    print("\n" + "="*50)
    print("SCREENING REPORT")
    print("="*50)
    
    for bucket in [Classification.GREEN, Classification.YELLOW, Classification.RED]:
        bucket_results = [r for r in results if r.classification == bucket]
        if bucket_results:
            print(f"\n{bucket.value} ({len(bucket_results)}):")
            for res in bucket_results:
                print(f"- {res.grant.foundation_name}: {res.rationale}")
                print(f"  Confidence: {res.confidence_score}, Amount: {res.grant.amount}")
                if res.sources:
                    print(f"  Sources: {', '.join(res.sources[:3])}")

    # 6. Summary Table
    print("\n" + "="*50)
    print("SUMMARY TABLE")
    print("="*50)
    
    table_data = []
    for res in results:
        sources_short = ", ".join([s.split('(')[0].strip() for s in res.sources]) if res.sources else "N/A"
        rationale_short = (res.rationale[:75] + '..') if len(res.rationale) > 75 else res.rationale
        
        table_data.append([
            res.grant.foundation_name,
            res.classification.value,
            res.confidence_score,
            rationale_short,
            sources_short
        ])
    
    headers = ["Foundation", "Class", "Conf", "Rationale", "Sources"]
    print(tabulate(table_data, headers=headers, tablefmt="grid"))

    if sheets:
        print("\nAll results written to Google Sheets.")


if __name__ == "__main__":
    main()

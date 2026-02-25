"""
count_backlog.py - check total grants in LOI Backlog and stage breakdown.
Run: python count_backlog.py
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8")
from dotenv import load_dotenv
load_dotenv()

from src.db_connector import DBConnector

db = DBConnector()
conn = db._get_connection()
cur = conn.cursor(dictionary=True)

# Total rows in the table
cur.execute("SELECT COUNT(*) AS total FROM Salesforce.Grant_Opportunities")
print("Total rows in Grant_Opportunities:", cur.fetchone()["total"])

# Breakdown by StageName
cur.execute("""
    SELECT StageName, COUNT(*) AS cnt
    FROM Salesforce.Grant_Opportunities
    GROUP BY StageName
    ORDER BY cnt DESC
    LIMIT 15
""")
rows = cur.fetchall()
print("\nStage breakdown:")
for r in rows:
    marker = "  <-- backlog" if r["StageName"] == "LOI Backlog" else ""
    print(f"  {str(r['StageName']):40s} {r['cnt']}{marker}")

cur.close()
conn.close()

import sqlite3
import json
import csv
import pandas as pd  # Requires 'pandas' and 'openpyxl' libraries

conn = sqlite3.connect("data/raw_repository.db")
conn.row_factory = sqlite3.Row
cursor = conn.cursor()
cursor.execute("""
    SELECT s.title, s.source_domain, s.published_utc, p.summary, p.iocs_json, p.threat_metadata_json, p.mitre_techniques_json
    FROM staging_raw s JOIN processed_articles p ON s.metadata_hash = p.metadata_hash
""")
rows = [dict(row) for row in cursor.fetchall()]

# Ensure there is data to export before proceeding
if rows:
    # 1. Export to JSON
    with open("output/processed.json", "w", encoding='utf-8') as f:
        json.dump(rows, f, indent=2, default=str)

    # 2. Export to CSV
    with open("output/processed.csv", "w", newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    # 3. Export to Excel (New Addition)
    df = pd.DataFrame(rows)
    # Convert any complex dictionary/list columns to string to prevent Excel errors
    for col in df.columns:
        if df[col].apply(lambda x: isinstance(x, (dict, list))).any():
            df[col] = df[col].apply(lambda x: json.dumps(x) if isinstance(x, (dict, list)) else x)
            
    df.to_excel("output/processed.xlsx", index=False, engine='openpyxl')
    
    print("Exported to output/ (JSON, CSV, and Excel)")
else:
    print("No data found to export.")

conn.close()

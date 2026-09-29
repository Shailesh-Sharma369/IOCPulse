import sqlite3
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font

DB_PATH = Path("data/raw_repository.db")
OUTPUT_FILE = Path("output/cti_articles.xlsx")


def export_to_excel():
    if not DB_PATH.exists():
        print(f"Database not found: {DB_PATH}")
        return

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id,
            source_domain,
            title,
            author,
            published_utc,
            source_status,
            source_url,
            original_source_url,
            status,
            retrieved_utc
        FROM staging_raw
        ORDER BY
            published_utc DESC,
            retrieved_utc DESC;
    """)

    rows = cursor.fetchall()

    wb = Workbook()
    ws = wb.active
    ws.title = "Threat Intelligence"

    headers = [
        "ID",
        "Source",
        "Title",
        "Author",
        "Published UTC",
        "Source Status",
        "Mirror URL",
        "Original Source URL",
        "Pipeline Status",
        "Retrieved UTC"
    ]

    for col, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col)
        cell.value = header
        cell.font = Font(bold=True)

    for row in rows:
        ws.append(row)

    # Auto-size columns
    for column_cells in ws.columns:
        length = max(len(str(cell.value)) if cell.value else 0 for cell in column_cells)
        ws.column_dimensions[column_cells[0].column_letter].width = min(length + 5, 60)

    wb.save(OUTPUT_FILE)

    conn.close()

    print(f"\nExported {len(rows)} articles")
    print(f"Excel saved to: {OUTPUT_FILE.resolve()}")


if __name__ == "__main__":
    export_to_excel()
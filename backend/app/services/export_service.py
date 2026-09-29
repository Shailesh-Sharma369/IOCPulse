import json
import csv
import io
from typing import List, Dict, Any, Optional
from datetime import datetime
from src.shared.database import DatabaseClient

class ExportService:
    def __init__(self, db: DatabaseClient):
        self.db = db

    async def get_processed_data(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fetch processed articles with filters (source, date range, etc.)"""
        where_clauses = []
        params = []
        if filters.get("source_domain"):
            where_clauses.append("s.source_domain = ?")
            params.append(filters["source_domain"])
        if filters.get("date_from"):
            where_clauses.append("s.published_utc >= ?")
            params.append(filters["date_from"])
        if filters.get("date_to"):
            where_clauses.append("s.published_utc <= ?")
            params.append(filters["date_to"])
        # Optionally filter by threat type, IOC type – not implemented in backend yet, skip.

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        query = f"""
            SELECT
                s.id, s.source_domain, s.title, s.author, s.published_utc,
                s.source_url, s.original_source_url, s.source_status,
                p.summary, p.iocs_json, p.threat_metadata_json,
                p.mitre_techniques_json, p.confidence_score, p.verification_status,
                p.processing_status, p.processing_timestamp,
                p.llm_raw_response, p.evidence_json, p.target_organization
            FROM staging_raw s
            JOIN processed_articles p ON s.metadata_hash = p.metadata_hash
            WHERE {where_sql}
            ORDER BY s.published_utc DESC
        """
        cursor = await self.db._conn.execute(query, params)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    def generate_csv(self, data: List[Dict[str, Any]]) -> bytes:
        if not data:
            return b""
        # Flatten JSON fields for CSV
        output = []
        for row in data:
            flat = row.copy()
            for col in ["iocs_json", "threat_metadata_json", "mitre_techniques_json", "evidence_json", "target_organization"]:
                if col in flat and flat[col]:
                    try:
                        flat[col] = json.dumps(json.loads(flat[col]), ensure_ascii=False)
                    except:
                        flat[col] = flat[col]
            output.append(flat)
        # Write CSV
        fieldnames = list(output[0].keys())
        output_io = io.StringIO()
        writer = csv.DictWriter(output_io, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output)
        return output_io.getvalue().encode("utf-8")

    def generate_json(self, data: List[Dict[str, Any]]) -> bytes:
        return json.dumps(data, indent=2, default=str).encode("utf-8")

    def generate_stix(self, data: List[Dict[str, Any]]) -> bytes:
        # Simplified STIX generation (placeholder)
        # In real implementation, use stix2 library
        return json.dumps({"error": "STIX export not implemented"}), 400
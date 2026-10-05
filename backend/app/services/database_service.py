from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from src.shared.database import DatabaseClient


class DatabaseService:
    """Encapsulates all read-only database queries for the API."""

    def __init__(self, db: DatabaseClient):
        self.db = db

    # ---------- Dashboard Stats ----------
    async def get_dashboard_stats(self) -> Dict[str, int]:
        cursor = await self.db._conn.execute("SELECT COUNT(*) FROM staging_raw")
        total = (await cursor.fetchone())[0]
        cursor = await self.db._conn.execute("SELECT COUNT(*) FROM staging_raw WHERE status='PENDING'")
        pending = (await cursor.fetchone())[0]
        cursor = await self.db._conn.execute("SELECT COUNT(*) FROM staging_raw WHERE status='PROCESSED'")
        processed = (await cursor.fetchone())[0]
        cursor = await self.db._conn.execute("SELECT COUNT(*) FROM staging_raw WHERE status='FAILED'")
        failed = (await cursor.fetchone())[0]
        return {
            "total_raw": total,
            "pending": pending,
            "processed": processed,
            "failed": failed,
        }

    # ---------- Raw Articles ----------
    async def get_raw_articles(
        self,
        filters: Dict[str, Any],
        offset: int,
        limit: int,
        sort_by: str = "published_utc",
        sort_dir: str = "DESC",
    ) -> Tuple[List[Dict[str, Any]], int]:
        where_clauses = []
        params: List[Any] = []
        if filters.get("search"):
            where_clauses.append("(title LIKE ? OR raw_html LIKE ?)")
            search_term = f"%{filters['search']}%"
            params.append(search_term)
            params.append(search_term)
        if filters.get("source_domain"):
            where_clauses.append("source_domain = ?")
            params.append(filters["source_domain"])
        if filters.get("status"):
            where_clauses.append("status = ?")
            params.append(filters["status"])
        if filters.get("date_from"):
            where_clauses.append("published_utc >= ?")
            params.append(filters["date_from"])
        if filters.get("date_to"):
            where_clauses.append("published_utc <= ?")
            params.append(filters["date_to"])

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        count_query = f"SELECT COUNT(*) FROM staging_raw WHERE {where_sql}"
        cursor = await self.db._conn.execute(count_query, params)
        total = (await cursor.fetchone())[0]

        order = f"{sort_by} {sort_dir}"
        query = f"""
            SELECT * FROM staging_raw
            WHERE {where_sql}
            ORDER BY {order}
            LIMIT ? OFFSET ?
        """
        params_ext = params + [limit, offset]
        cursor = await self.db._conn.execute(query, params_ext)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows], total

    async def get_raw_article_by_id(self, article_id: int) -> Optional[Dict[str, Any]]:
        cursor = await self.db._conn.execute(
            "SELECT * FROM staging_raw WHERE id = ?", (article_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    # ---------- Processed Articles (joined) ----------
    async def get_processed_articles(
        self,
        filters: Dict[str, Any],
        offset: int,
        limit: int,
        sort_by: str = "p.processing_timestamp",
        sort_dir: str = "DESC",
    ) -> Tuple[List[Dict[str, Any]], int]:
        where_clauses = []
        params: List[Any] = []
        if filters.get("source_domain"):
            where_clauses.append("s.source_domain = ?")
            params.append(filters["source_domain"])
        if filters.get("confidence_min") is not None:
            where_clauses.append("p.confidence_score >= ?")
            params.append(filters["confidence_min"])
        if filters.get("verification_status"):
            where_clauses.append("p.verification_status = ?")
            params.append(filters["verification_status"])
        if filters.get("severity"):
            where_clauses.append("p.severity = ?")
            params.append(filters["severity"])
        if filters.get("tlp_tag"):
            where_clauses.append("p.tlp_tag = ?")
            params.append(filters["tlp_tag"])
        if filters.get("date_from"):
            where_clauses.append("s.published_utc >= ?")
            params.append(filters["date_from"])
        if filters.get("date_to"):
            where_clauses.append("s.published_utc <= ?")
            params.append(filters["date_to"])

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        count_query = f"""
            SELECT COUNT(*)
            FROM staging_raw s
            JOIN processed_articles p ON s.metadata_hash = p.metadata_hash
            WHERE {where_sql}
        """
        cursor = await self.db._conn.execute(count_query, params)
        total = (await cursor.fetchone())[0]

        order = f"{sort_by} {sort_dir}"
        query = f"""
            SELECT
                s.id, s.metadata_hash, s.source_domain, s.source_url,
                s.title, s.author, s.published_utc, s.original_source_url,
                s.source_status, s.retrieved_utc, s.status, s.processing_error,
                p.summary, p.iocs_json, p.threat_metadata_json,
                p.mitre_techniques_json, p.llm_raw_response,
                p.processing_status, p.processing_timestamp,
                p.confidence_score, p.verification_status,
                p.hallucination_count, p.evidence_json, p.target_organization,
                p.severity, p.tlp_tag, p.cve_details_json
            FROM staging_raw s
            JOIN processed_articles p ON s.metadata_hash = p.metadata_hash
            WHERE {where_sql}
            ORDER BY {order}
            LIMIT ? OFFSET ?
        """
        params_ext = params + [limit, offset]
        cursor = await self.db._conn.execute(query, params_ext)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows], total

    async def get_processed_article_by_id(self, article_id: int) -> Optional[Dict[str, Any]]:
        query = """
            SELECT
                s.id, s.metadata_hash, s.source_domain, s.source_url,
                s.title, s.author, s.published_utc, s.original_source_url,
                s.source_status, s.retrieved_utc, s.status, s.processing_error,
                p.summary, p.iocs_json, p.threat_metadata_json,
                p.mitre_techniques_json, p.llm_raw_response,
                p.processing_status, p.processing_timestamp,
                p.confidence_score, p.verification_status,
                p.hallucination_count, p.evidence_json, p.target_organization,
                p.severity, p.tlp_tag, p.cve_details_json
            FROM staging_raw s
            JOIN processed_articles p ON s.metadata_hash = p.metadata_hash
            WHERE s.id = ?
        """
        cursor = await self.db._conn.execute(query, (article_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None
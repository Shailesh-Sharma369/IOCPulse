import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
import aiosqlite
from src.core.config import settings

logger = logging.getLogger(__name__)


class DatabaseClient:
    """
    Async SQLite client (aiosqlite only). Local file-based storage so anyone
    can clone the repo and run it with zero external services.
    """

    def __init__(self, db_path: str = settings.DB_PATH):
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None

    async def __aenter__(self):
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._init_tables()
        logger.info("Connected to local SQLite database at %s", self.db_path)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._conn:
            await self._conn.close()

    # ------------------------------------------------------------------ #
    #  Schema
    # ------------------------------------------------------------------ #
    async def _init_tables(self):
        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS staging_raw (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                metadata_hash TEXT UNIQUE NOT NULL,
                source_domain TEXT NOT NULL,
                source_url TEXT NOT NULL,
                title TEXT,
                author TEXT,
                published_utc DATETIME,
                raw_html TEXT,
                original_source_url TEXT,
                source_status TEXT DEFAULT 'MIRROR',
                retrieved_utc DATETIME DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'PENDING',
                processing_error TEXT
            )
        """)

        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS processed_articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                metadata_hash TEXT NOT NULL UNIQUE REFERENCES staging_raw(metadata_hash),
                summary TEXT,
                iocs_json TEXT,
                threat_metadata_json TEXT,
                mitre_techniques_json TEXT,
                llm_raw_response TEXT,
                processing_status TEXT DEFAULT 'PENDING',
                processing_error TEXT,
                processing_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                confidence_score INTEGER DEFAULT 0,
                verification_status TEXT DEFAULT 'unknown',
                hallucination_count INTEGER DEFAULT 0,
                evidence_json TEXT,
                target_organization TEXT DEFAULT '[]',
                severity TEXT DEFAULT 'Unknown',         -- NEW
                tlp_tag  TEXT DEFAULT 'TLP:CLEAR'        -- NEW
            )
        """)

        # Backward-compatible column adds (safe on fresh DBs and old DBs).
        # NOTE: SQLite ALTER TABLE ADD COLUMN with a literal DEFAULT is fast
        # and does not rewrite the table — safe for large existing DBs.
        new_columns = [
            ("confidence_score",    "INTEGER DEFAULT 0"),
            ("verification_status", "TEXT DEFAULT 'unknown'"),
            ("hallucination_count", "INTEGER DEFAULT 0"),
            ("evidence_json",       "TEXT"),
            ("target_organization", "TEXT DEFAULT '[]'"),
            ("severity",            "TEXT DEFAULT 'Unknown'"),      # NEW
            ("tlp_tag",             "TEXT DEFAULT 'TLP:CLEAR'"),    # NEW
        ]
        for col_name, col_type in new_columns:
            try:
                await self._conn.execute(
                    f"ALTER TABLE processed_articles ADD COLUMN {col_name} {col_type}"
                )
            except Exception:
                # Column already exists — ignore
                pass

        await self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_staging_hash ON staging_raw(metadata_hash)"
        )
        await self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_staging_published ON staging_raw(published_utc)"
        )
        await self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_staging_status ON staging_raw(status)"
        )
        # Indexes to speed up future severity/TLP filtering
        await self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_processed_severity ON processed_articles(severity)"
        )
        await self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_processed_tlp ON processed_articles(tlp_tag)"
        )
        await self._conn.commit()

    # ------------------------------------------------------------------ #
    #  Data methods
    # ------------------------------------------------------------------ #
    async def insert_raw_article(self, article: dict) -> int:
        cursor = await self._conn.execute("""
            INSERT OR IGNORE INTO staging_raw
            (metadata_hash, source_domain, source_url, title, author,
             published_utc, raw_html, original_source_url, source_status, status)
            VALUES (:metadata_hash, :source_domain, :source_url, :title, :author,
                    :published_utc, :raw_html, :original_source_url, :source_status, 'PENDING')
        """, article)
        await self._conn.commit()
        return cursor.lastrowid if cursor.lastrowid else 0

    async def get_pending_articles(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        query = "SELECT * FROM staging_raw WHERE status='PENDING' ORDER BY published_utc DESC"
        if limit:
            # Cast to int to prevent SQL injection if `limit` ever comes from user input
            query += f" LIMIT {int(limit)}"
        cursor = await self._conn.execute(query)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def update_article_status(self, metadata_hash: str, status: str, error: str = None):
        await self._conn.execute(
            "UPDATE staging_raw SET status=?, processing_error=? WHERE metadata_hash=?",
            (status, error, metadata_hash),
        )
        await self._conn.commit()

    async def insert_processed_article(
        self,
        metadata_hash: str,
        summary: str,
        iocs_json: str,
        threat_metadata_json: str,
        mitre_techniques_json: str,
        llm_raw_response: str,
        confidence_score: int = 0,
        verification_status: str = 'unknown',
        hallucination_count: int = 0,
        evidence_json: str = None,
        target_organization_json: str = '[]',
        severity: str = "Unknown",           # NEW
        tlp_tag:  str = "TLP:CLEAR",         # NEW
    ):
        await self._conn.execute("""
            INSERT OR REPLACE INTO processed_articles
            (metadata_hash, summary, iocs_json, threat_metadata_json, mitre_techniques_json,
             llm_raw_response, processing_status, confidence_score, verification_status,
             hallucination_count, evidence_json, target_organization, severity, tlp_tag)
            VALUES (?, ?, ?, ?, ?, ?, 'SUCCESS', ?, ?, ?, ?, ?, ?, ?)
        """, (
            metadata_hash, summary, iocs_json, threat_metadata_json, mitre_techniques_json,
            llm_raw_response, confidence_score, verification_status,
            hallucination_count, evidence_json, target_organization_json,
            severity, tlp_tag,
        ))
        await self._conn.commit()
import os
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

try:
    import libsql_client
except ImportError:
    libsql_client = None

import aiosqlite
from src.core.config import settings

logger = logging.getLogger(__name__)

class TursoRow:
    """Row wrapper that supports both index lookup (row[0]) and key lookup (row['col'])."""
    def __init__(self, columns, values):
        self.columns = list(columns)
        self.values = list(values)
        self._map = dict(zip(self.columns, self.values))

    def __getitem__(self, key):
        if isinstance(key, int):
            return self.values[key]
        return self._map[key]

    def keys(self):
        return self._map.keys()

    def __iter__(self):
        return iter(self._map)

    def get(self, key, default=None):
        return self._map.get(key, default)

    def __repr__(self):
        return repr(self._map)

class TursoCursorWrapper:
    """Wrapper to make libsql_client result behave like a cursor."""
    def __init__(self, result):
        columns = getattr(result, 'columns', [])
        self.rows = []
        if hasattr(result, 'rows'):
            for r in result.rows:
                vals = tuple(r) if not isinstance(r, dict) else tuple(r.values())
                cols = columns if columns else [f"col_{i}" for i in range(len(vals))]
                self.rows.append(TursoRow(cols, vals))
        self.lastrowid = getattr(result, 'last_insert_rowid', 0)

    async def fetchall(self):
        return self.rows

    async def fetchone(self):
        return self.rows[0] if self.rows else None

class TursoConnWrapper:
    """Wrapper to make libsql_client behave like aiosqlite connection."""
    def __init__(self, client):
        self.client = client

    async def execute(self, query: str, params=()):
        if isinstance(params, dict):
            clean_params = {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in params.items()}
        else:
            clean_params = tuple(v.isoformat() if isinstance(v, datetime) else v for v in params)

        res = await self.client.execute(query, clean_params)
        return TursoCursorWrapper(res)

    async def commit(self):
        pass


class DatabaseClient:
    def __init__(self, db_path: str = settings.DB_PATH):
        self.db_path = db_path
        self._conn = None
        self._turso_client = None

    async def __aenter__(self):
        turso_url = os.getenv("TURSO_DATABASE_URL")
        turso_token = os.getenv("TURSO_AUTH_TOKEN")

        if turso_url and turso_token and libsql_client is not None:
            # Use Turso (remote SQLite)
            self._turso_client = libsql_client.create_client(url=turso_url, auth_token=turso_token)
            self._conn = TursoConnWrapper(self._turso_client)
            logger.info("Connected to Turso database")
        else:
            # Fallback to local SQLite
            self._conn = await aiosqlite.connect(self.db_path)
            self._conn.row_factory = aiosqlite.Row
            logger.info("Connected to local SQLite database")

        await self._init_tables()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._turso_client:
            await self._turso_client.close()
        elif self._conn:
            await self._conn.close()

    # ========================================================================
    #  ORIGINAL TABLE INITIALISATION – UNCHANGED
    # ========================================================================
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
                target_organization TEXT DEFAULT '[]'
            )
        """)

        # Add new columns if they don't exist (backward compatibility)
        new_columns = [
            ("confidence_score", "INTEGER DEFAULT 0"),
            ("verification_status", "TEXT DEFAULT 'unknown'"),
            ("hallucination_count", "INTEGER DEFAULT 0"),
            ("evidence_json", "TEXT"),
            ("target_organization", "TEXT DEFAULT '[]'")
        ]
        for col_name, col_type in new_columns:
            try:
                await self._conn.execute(f"ALTER TABLE processed_articles ADD COLUMN {col_name} {col_type}")
            except Exception:
                # Column already exists – ignore
                pass

        await self._conn.execute("CREATE INDEX IF NOT EXISTS idx_staging_hash ON staging_raw(metadata_hash)")
        await self._conn.execute("CREATE INDEX IF NOT EXISTS idx_staging_published ON staging_raw(published_utc)")
        await self._conn.execute("CREATE INDEX IF NOT EXISTS idx_staging_status ON staging_raw(status)")
        await self._conn.commit()

    # ========================================================================
    #  ORIGINAL DATA METHODS – UNCHANGED
    # ========================================================================
    async def insert_raw_article(self, article: dict) -> int:
        # FIX: Removed 'async with' to prevent Turso coroutine __aexit__ error
        cursor = await self._conn.execute("""
            INSERT OR IGNORE INTO staging_raw
            (metadata_hash, source_domain, source_url, title, author, published_utc, raw_html, original_source_url, source_status, status)
            VALUES (:metadata_hash, :source_domain, :source_url, :title, :author, :published_utc, :raw_html, :original_source_url, :source_status, 'PENDING')
        """, article)
        await self._conn.commit()
        return cursor.lastrowid if cursor.lastrowid else 0

    async def get_pending_articles(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        query = "SELECT * FROM staging_raw WHERE status='PENDING' ORDER BY published_utc DESC"
        if limit:
            query += f" LIMIT {limit}"
        cursor = await self._conn.execute(query)
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def update_article_status(self, metadata_hash: str, status: str, error: str = None):
        await self._conn.execute(
            "UPDATE staging_raw SET status=?, processing_error=? WHERE metadata_hash=?",
            (status, error, metadata_hash)
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
        target_organization_json: str = '[]'
    ):
        await self._conn.execute("""
            INSERT OR REPLACE INTO processed_articles
            (metadata_hash, summary, iocs_json, threat_metadata_json, mitre_techniques_json,
             llm_raw_response, processing_status, confidence_score, verification_status,
             hallucination_count, evidence_json, target_organization)
            VALUES (?, ?, ?, ?, ?, ?, 'SUCCESS', ?, ?, ?, ?, ?)
        """, (
            metadata_hash, summary, iocs_json, threat_metadata_json, mitre_techniques_json,
            llm_raw_response, confidence_score, verification_status,
            hallucination_count, evidence_json, target_organization_json
        ))
        await self._conn.commit()
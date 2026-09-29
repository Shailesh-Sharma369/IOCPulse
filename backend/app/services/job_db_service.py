import logging
from datetime import datetime, timezone
from typing import Optional
from src.shared.database import DatabaseClient

logger = logging.getLogger(__name__)

class JobDBService:
    """
    Manages persistent job history in the same SQLite database.
    The table is created on the first use.
    """
    def __init__(self, db: DatabaseClient):
        self.db = db

    async def _ensure_table(self):
        await self.db._conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                type TEXT,
                status TEXT,
                created_at DATETIME,
                updated_at DATETIME,
                result INTEGER,
                error TEXT
            )
        """)
        await self.db._conn.commit()

    async def insert_job(self, job_id: str, job_type: str, status: str, created_at: datetime):
        await self._ensure_table()
        await self.db._conn.execute(
            "INSERT INTO jobs (job_id, type, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (job_id, job_type, status, created_at, created_at)
        )
        await self.db._conn.commit()

    async def update_job(self, job_id: str, status: str, updated_at: datetime, result: Optional[int] = None, error: Optional[str] = None):
        await self._ensure_table()
        await self.db._conn.execute(
            "UPDATE jobs SET status = ?, updated_at = ?, result = ?, error = ? WHERE job_id = ?",
            (status, updated_at, result, error, job_id)
        )
        await self.db._conn.commit()

    async def get_recent_jobs(self, limit: int = 10):
        await self._ensure_table()
        cursor = await self.db._conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
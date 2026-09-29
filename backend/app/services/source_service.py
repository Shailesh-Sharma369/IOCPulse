import logging
from typing import List, Dict, Any
from src.core.config import settings
from src.shared.database import DatabaseClient

logger = logging.getLogger(__name__)

class SourceService:
    def __init__(self, db: DatabaseClient):
        self.db = db

    async def get_all_sources(self) -> List[Dict[str, Any]]:
        """Return combined built‑in + user sources."""
        # Built‑in sources
        builtin = [
            {
                "id": f"builtin_{i}",
                "name": s.get("name"),
                "base_url": s.get("base_url"),
                "rss_url": s.get("rss_url"),
                "use_playwright": s.get("use_playwright", False),
                "is_user": False,
            }
            for i, s in enumerate(settings.SOURCES)
        ]

        # User sources from `user_sources` table
        user = []
        try:
            # Ensure table exists (already created by Streamlit or we can create here)
            await self.db._conn.execute("""
                CREATE TABLE IF NOT EXISTS user_sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    base_url TEXT NOT NULL,
                    rss_url TEXT,
                    use_playwright INTEGER DEFAULT 0
                )
            """)
            await self.db._conn.commit()
            cursor = await self.db._conn.execute("SELECT * FROM user_sources ORDER BY name")
            rows = await cursor.fetchall()
            for row in rows:
                user.append({
                    "id": f"user_{row['id']}",
                    "name": row["name"],
                    "base_url": row["base_url"],
                    "rss_url": row.get("rss_url"),
                    "use_playwright": bool(row.get("use_playwright", 0)),
                    "is_user": True,
                })
        except Exception as e:
            logger.warning(f"Failed to fetch user sources: {e}")

        return builtin + user
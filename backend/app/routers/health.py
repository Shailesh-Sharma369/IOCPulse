from fastapi import APIRouter, Depends
from src.shared.database import DatabaseClient
from app.dependencies import get_db

router = APIRouter(tags=["health"])

@router.get("/health")
async def health_check():
    return {"status": "ok"}

@router.get("/health/db")
async def db_health_check(db: DatabaseClient = Depends(get_db)):
    try:
        # Execute a simple query to verify connectivity
        cursor = await db._conn.execute("SELECT 1")
        await cursor.fetchone()
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        return {"status": "error", "database": "unreachable", "detail": str(e)}
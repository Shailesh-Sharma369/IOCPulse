from fastapi import Depends
from src.shared.database import DatabaseClient
from app.config import settings

async def get_db() :
    """
    Dependency that yields a DatabaseClient instance.
    The client is closed when the request ends.
    """
    db = DatabaseClient(settings.DB_PATH)
    await db.__aenter__()
    try:
        yield db
    finally:
        await db.__aexit__(None, None, None)
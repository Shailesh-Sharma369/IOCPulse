from fastapi import APIRouter, Depends
from src.shared.database import DatabaseClient
from app.dependencies import get_db
from app.services.source_service import SourceService
from app.utils.response import success_response

router = APIRouter(prefix="/api/v1/sources", tags=["sources"])

@router.get("")
async def list_sources(db: DatabaseClient = Depends(get_db)):
    service = SourceService(db)
    sources = await service.get_all_sources()
    return success_response(data=sources)
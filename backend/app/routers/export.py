from fastapi import APIRouter, Depends, Query, HTTPException
from typing import Optional
from datetime import datetime
from src.shared.database import DatabaseClient
from app.dependencies import get_db
from app.services.export_service import ExportService
from fastapi.responses import Response, StreamingResponse
import io

router = APIRouter(prefix="/api/v1/export", tags=["export"])

@router.get("/csv")
async def export_csv(
    source_domain: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    db: DatabaseClient = Depends(get_db)
):
    filters = {}
    if source_domain:
        filters["source_domain"] = source_domain
    if date_from:
        filters["date_from"] = date_from
    if date_to:
        filters["date_to"] = date_to

    service = ExportService(db)
    data = await service.get_processed_data(filters)
    csv_data = service.generate_csv(data)
    filename = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@router.get("/json")
async def export_json(
    source_domain: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    db: DatabaseClient = Depends(get_db)
):
    filters = {}
    if source_domain:
        filters["source_domain"] = source_domain
    if date_from:
        filters["date_from"] = date_from
    if date_to:
        filters["date_to"] = date_to

    service = ExportService(db)
    data = await service.get_processed_data(filters)
    json_data = service.generate_json(data)
    filename = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    return Response(
        content=json_data,
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@router.get("/stix")
async def export_stix(
    source_domain: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    db: DatabaseClient = Depends(get_db)
):
    # Placeholder – not fully implemented
    return {"error": "STIX export not yet implemented"}
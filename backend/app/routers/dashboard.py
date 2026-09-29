from fastapi import APIRouter, Depends
from src.shared.database import DatabaseClient
from app.dependencies import get_db
from app.services.database_service import DatabaseService
from app.services.dashboard_service import DashboardService
from app.utils.response import success_response

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])

@router.get("")
async def get_dashboard(db: DatabaseClient = Depends(get_db)):
    db_service = DatabaseService(db)
    dashboard_service = DashboardService(db_service)
    metrics = await dashboard_service.get_metrics()
    return success_response(data=metrics)
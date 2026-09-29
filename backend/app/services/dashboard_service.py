from app.services.database_service import DatabaseService

class DashboardService:
    def __init__(self, db_service: DatabaseService):
        self.db_service = db_service

    async def get_metrics(self):
        stats = await self.db_service.get_dashboard_stats()
        return stats
from pydantic import BaseModel

class DashboardMetrics(BaseModel):
    total_raw: int
    pending: int
    processed: int
    failed: int
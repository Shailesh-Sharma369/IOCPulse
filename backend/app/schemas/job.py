from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
from app.models.job_state import JobStatus

class JobStartRequest(BaseModel):
    sources: Optional[List[str]] = Field(
        None, description="List of source names to ingest. If omitted, all sources are used."
    )
    start_date: Optional[datetime] = Field(
        None, description="Start date for filtering articles (UTC)."
    )
    end_date: Optional[datetime] = Field(
        None, description="End date for filtering articles (UTC)."
    )
    limit: Optional[int] = Field(
        None, ge=1, description="Maximum number of articles to process (processing only)."
    )

class JobResponse(BaseModel):
    job_id: str
    type: str  # "ingestion" or "processing"
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    error: Optional[str] = None
    result: Optional[int] = Field(None, description="Number of articles ingested/processed.")
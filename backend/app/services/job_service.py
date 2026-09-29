import uuid
import asyncio
from datetime import datetime, timezone
from typing import Dict, Optional, List
from app.models.job_state import JobStatus
from app.schemas.job import JobResponse
from app.services.job_db_service import JobDBService
from src.shared.database import DatabaseClient

class JobService:
    MAX_STORED_JOBS = 100

    def __init__(self):
        self._jobs: Dict[str, Dict] = {}
        self._running_ingestion = False
        self._running_processing = False
        self._lock = asyncio.Lock()

    def _cleanup_if_needed(self):
        if len(self._jobs) <= self.MAX_STORED_JOBS:
            return
        sorted_jobs = sorted(
            [j for j in self._jobs.values() if j["status"] != JobStatus.RUNNING],
            key=lambda x: x["created_at"]
        )
        for job in sorted_jobs[:len(sorted_jobs) - self.MAX_STORED_JOBS // 2]:
            self._jobs.pop(job.get("job_id"), None)

    async def create_job(self, job_type: str) -> str:
        async with self._lock:
            if job_type == "ingestion" and self._running_ingestion:
                raise RuntimeError("Ingestion job already running")
            if job_type == "processing" and self._running_processing:
                raise RuntimeError("Processing job already running")

            job_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc)
            self._jobs[job_id] = {
                "job_id": job_id,
                "type": job_type,
                "status": JobStatus.RUNNING,
                "created_at": now,
                "updated_at": now,
                "error": None,
                "result": None,
            }
            if job_type == "ingestion":
                self._running_ingestion = True
            else:
                self._running_processing = True

            self._cleanup_if_needed()
            return job_id

    async def get_job(self, job_id: str) -> Optional[JobResponse]:
        async with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            return JobResponse(**job)

    # ---------- FIXED: list_jobs reads from DB ----------
    async def list_jobs(self, limit: int = 20) -> List[JobResponse]:
        # Use JobDBService to fetch from persistent jobs table
        async with DatabaseClient() as db:
            job_db = JobDBService(db)
            rows = await job_db.get_recent_jobs(limit)
        # Convert rows (dicts) to JobResponse objects
        return [JobResponse(**row) for row in rows]

    async def update_job(
        self,
        job_id: str,
        status: JobStatus,
        error: Optional[str] = None,
        result: Optional[int] = None
    ) -> None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job["status"] = status
            job["updated_at"] = datetime.now(timezone.utc)
            if error is not None:
                job["error"] = error
            if result is not None:
                job["result"] = result

            if status in (JobStatus.COMPLETED, JobStatus.FAILED):
                if job["type"] == "ingestion":
                    self._running_ingestion = False
                else:
                    self._running_processing = False

    async def is_running(self, job_type: str) -> bool:
        async with self._lock:
            if job_type == "ingestion":
                return self._running_ingestion
            return self._running_processing

job_service = JobService()
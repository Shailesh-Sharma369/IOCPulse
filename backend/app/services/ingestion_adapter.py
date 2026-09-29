import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, List
from src.core.config import settings
from src.module_1_ingestion.source_manager import SourceManager
from app.services.job_service import job_service
from app.services.job_db_service import JobDBService
from app.models.job_state import JobStatus
from src.shared.database import DatabaseClient

logger = logging.getLogger(__name__)

_settings_lock = asyncio.Lock()

async def run_ingestion_job(
    job_id: str,
    sources: Optional[List[str]] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> None:
    """
    Background task that executes Module 1 ingestion.
    Temporarily overrides global settings and restores them afterwards.
    The lock is held for the entire duration to prevent race conditions.
    Also persists job status to the jobs table for history.
    """
    # Insert initial job record into DB (status = RUNNING)
    async with DatabaseClient() as db:
        job_db = JobDBService(db)
        await job_db.insert_job(job_id, "ingestion", JobStatus.RUNNING.value, datetime.now(timezone.utc))

    # Acquire the lock before modifying settings
    async with _settings_lock:
        original_sources = settings.SOURCES
        original_start = settings.START_DATE
        original_end = settings.END_DATE

        try:
            # Apply overrides
            if sources is not None:
                filtered = [s for s in settings.SOURCES if s.get("name") in sources]
                if filtered:
                    settings.SOURCES = filtered
                else:
                    logger.warning(f"No matching sources found for {sources}; using all.")
            if start_date is not None:
                settings.START_DATE = start_date
            if end_date is not None:
                settings.END_DATE = end_date

            logger.info(
                f"Ingestion job {job_id} started. Sources: {[s['name'] for s in settings.SOURCES]}, "
                f"Start: {settings.START_DATE}, End: {settings.END_DATE}"
            )

            # Run the ingestion (fully async)
            manager = SourceManager()
            count = await manager.ingest_and_persist()

            # Success
            await job_service.update_job(job_id, JobStatus.COMPLETED, result=count)
            # Update DB
            async with DatabaseClient() as db:
                job_db = JobDBService(db)
                await job_db.update_job(job_id, JobStatus.COMPLETED.value, datetime.now(timezone.utc), result=count)
            logger.info(f"Ingestion job {job_id} completed: {count} articles ingested.")

        except Exception as e:
            error_msg = f"Ingestion job {job_id} failed: {str(e)}"
            logger.exception(error_msg)
            await job_service.update_job(job_id, JobStatus.FAILED, error=error_msg)
            # Update DB
            async with DatabaseClient() as db:
                job_db = JobDBService(db)
                await job_db.update_job(job_id, JobStatus.FAILED.value, datetime.now(timezone.utc), error=error_msg)

        finally:
            # Always restore original settings
            settings.SOURCES = original_sources
            settings.START_DATE = original_start
            settings.END_DATE = original_end
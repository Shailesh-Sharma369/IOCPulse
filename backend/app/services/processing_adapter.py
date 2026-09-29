import logging
from datetime import datetime, timezone
from typing import Optional
from src.core.config import settings
from src.shared.database import DatabaseClient
from src.module_2_llm_processing.processor import ArticleProcessor
from src.module_2_llm_processing.llm_client import LLMClient
from app.services.job_service import job_service
from app.services.job_db_service import JobDBService
from app.models.job_state import JobStatus

logger = logging.getLogger(__name__)

async def run_processing_job(
    job_id: str,
    limit: Optional[int] = None
) -> None:
    """
    Background task that executes Module 2 LLM processing.
    Persists job status to the jobs table for history.
    """
    # Insert initial job record into DB (status = RUNNING)
    async with DatabaseClient() as db:
        job_db = JobDBService(db)
        await job_db.insert_job(job_id, "processing", JobStatus.RUNNING.value, datetime.now(timezone.utc))

    try:
        logger.info(f"Processing job {job_id} started with limit={limit}")

        # Build dependencies (all imported from src/)
        client = LLMClient(
            base_url=settings.LLM_SERVER_URL,
            timeout=settings.REQUEST_TIMEOUT_SECONDS
        )

        # DatabaseClient is an async context manager
        async with DatabaseClient() as db:
            processor = ArticleProcessor(
                llm_client=client,
                db=db,
                batch_size=settings.LLM_BATCH_SIZE
            )
            count = await processor.run(limit=limit)

        # Success
        await job_service.update_job(job_id, JobStatus.COMPLETED, result=count)
        # Update DB
        async with DatabaseClient() as db:
            job_db = JobDBService(db)
            await job_db.update_job(job_id, JobStatus.COMPLETED.value, datetime.now(timezone.utc), result=count)
        logger.info(f"Processing job {job_id} completed: {count} articles processed.")

    except Exception as e:
        error_msg = f"Processing job {job_id} failed: {str(e)}"
        logger.exception(error_msg)
        await job_service.update_job(job_id, JobStatus.FAILED, error=error_msg)
        # Update DB
        async with DatabaseClient() as db:
            job_db = JobDBService(db)
            await job_db.update_job(job_id, JobStatus.FAILED.value, datetime.now(timezone.utc), error=error_msg)
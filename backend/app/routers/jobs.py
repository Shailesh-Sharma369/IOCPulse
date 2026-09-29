from fastapi import APIRouter, HTTPException, Query
from app.schemas.job import JobStartRequest, JobResponse
from app.services.job_service import job_service
from app.services.ingestion_adapter import run_ingestion_job
from app.services.processing_adapter import run_processing_job
import asyncio

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])

@router.post("/ingestion/start", response_model=JobResponse, status_code=202)
async def start_ingestion(request: JobStartRequest):
    """
    Start a new ingestion (Module 1) job.
    Only one ingestion job can run at a time.
    """
    if await job_service.is_running("ingestion"):
        raise HTTPException(
            status_code=409,
            detail="An ingestion job is already running. Please wait for it to complete."
        )

    try:
        job_id = await job_service.create_job("ingestion")
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))

    # Fire-and-forget background task
    asyncio.create_task(run_ingestion_job(
        job_id,
        sources=request.sources,
        start_date=request.start_date,
        end_date=request.end_date,
    ))
    return await job_service.get_job(job_id)

@router.post("/processing/start", response_model=JobResponse, status_code=202)
async def start_processing(request: JobStartRequest):
    """
    Start a new LLM processing (Module 2) job.
    Only one processing job can run at a time.
    """
    if await job_service.is_running("processing"):
        raise HTTPException(
            status_code=409,
            detail="A processing job is already running. Please wait for it to complete."
        )

    try:
        job_id = await job_service.create_job("processing")
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))

    asyncio.create_task(run_processing_job(
        job_id,
        limit=request.limit,
    ))
    return await job_service.get_job(job_id)

@router.get("/{job_id}", response_model=JobResponse)
async def get_job_status(job_id: str):
    """
    Retrieve the status of a previously started job.
    """
    job = await job_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@router.get("/", response_model=list[JobResponse])
async def list_jobs(limit: int = Query(20, ge=1, le=100)):
    """
    List recent jobs (most recent first).
    """
    return await job_service.list_jobs(limit)
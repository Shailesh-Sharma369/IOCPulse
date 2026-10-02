import sys
import os
import logging
from pathlib import Path
from contextlib import asynccontextmanager

# Add project root to sys.path to allow importing src/
ROOT_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor

from app.config import get_cors_origins
from app.routers import (
    health_router,
    dashboard_router,
    articles_raw_router,
    articles_processed_router,
)
from app.utils.response import error_response
from app.utils.exceptions import NotFoundError, ValidationError

from app.routers.sources import router as sources_router
from app.routers.export import router as export_router
from app.routers.jobs import router as jobs_router
from app.routers.dashboard_analytics import router as dashboard_analytics_router

from app.services.job_service import job_service


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Scheduler configuration (env-tunable, secure-by-default)
# ---------------------------------------------------------------------------
ENABLE_SCHEDULER = os.getenv("ENABLE_SCHEDULER", "true").lower() == "true"
SCHEDULER_HOUR_UTC = int(os.getenv("SCHEDULER_HOUR_UTC", "4"))


async def _scheduled_ingestion_tick() -> None:
    """
    Fires once per day at SCHEDULER_HOUR_UTC:00 UTC.

    Guardrails:
      - Lazy-imports run_ingestion_job to avoid an import cycle
        (main → ingestion_adapter → job_service → main).
      - Uses job_service.create_job("ingestion"), which raises RuntimeError
        if another ingestion is already RUNNING. This prevents overlap between
        the scheduled run and any manual run started from the Jobs API.
      - Never propagates exceptions — the scheduler must not crash the loop.
    """
    # Lazy import: keep top-level imports clean and avoid a circular dependency
    from app.services.ingestion_adapter import run_ingestion_job

    # Concurrency guard — same guardrail as the /jobs/ingestion/start endpoint
    try:
        if await job_service.is_running("ingestion"):
            logger.warning(
                "Scheduled ingestion skipped: another ingestion job is already running."
            )
            return
        job_id = await job_service.create_job("ingestion")
    except RuntimeError as exc:
        logger.warning("Scheduled ingestion skipped: %s", exc)
        return
    except Exception:
        logger.exception("Scheduled ingestion aborted before start (unexpected error).")
        return

    logger.info("Scheduled ingestion starting (job_id=%s)", job_id)
    try:
        # run_ingestion_job already updates job_service on success/failure
        # and persists to the jobs table; we only log here.
        await run_ingestion_job(job_id)
    except Exception:
        logger.exception("Scheduled ingestion job %s crashed.", job_id)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ------------------------------------------------------------------ #
    # Startup
    # ------------------------------------------------------------------ #
    scheduler: AsyncIOScheduler | None = None

    if ENABLE_SCHEDULER:
        scheduler = AsyncIOScheduler(
            jobstores={"default": MemoryJobStore()},
            executors={"default": AsyncIOExecutor()},
            job_defaults={
                "coalesce": True,            # Collapse missed runs into one
                "max_instances": 1,          # Never run concurrently
                "misfire_grace_time": 3600,  # 1h grace window for late runs
            },
            timezone="UTC",
        )
        scheduler.add_job(
            _scheduled_ingestion_tick,
            trigger=CronTrigger(hour=SCHEDULER_HOUR_UTC, minute=0, timezone="UTC"),
            id="daily_ingestion",
            name=f"Daily CTI ingestion @ {SCHEDULER_HOUR_UTC:02d}:00 UTC",
            replace_existing=True,
        )
        scheduler.start()
        logger.info(
            "AsyncIOScheduler started — daily ingestion at %02d:00 UTC.",
            SCHEDULER_HOUR_UTC,
        )
    else:
        logger.info("Scheduler disabled (ENABLE_SCHEDULER=false).")

    try:
        yield
    finally:
        # ------------------------------------------------------------------ #
        # Shutdown — must be idempotent, must never raise
        # ------------------------------------------------------------------ #
        if scheduler is not None:
            logger.info("Shutting down AsyncIOScheduler…")
            try:
                # wait=False → do not block the event loop on shutdown
                scheduler.shutdown(wait=False)
            except Exception:
                logger.exception("Error during scheduler shutdown (non-fatal).")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="CTI Platform API",
    version="1.1.0",
    description="Backend for Cyber Threat Intelligence Platform – IOC Pulse",
    lifespan=lifespan,
)

# CORS — origins are driven by ALLOWED_ORIGINS in .env ("*" default for dev).
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(health_router)
app.include_router(dashboard_router)
app.include_router(articles_raw_router)
app.include_router(articles_processed_router)
app.include_router(jobs_router)
app.include_router(sources_router)
app.include_router(export_router)
app.include_router(dashboard_analytics_router)


# ---------------------------------------------------------------------------
# Global exception handlers
# ---------------------------------------------------------------------------
@app.exception_handler(NotFoundError)
async def not_found_handler(request, exc):
    return error_response(str(exc), status_code=404)


@app.exception_handler(ValidationError)
async def validation_handler(request, exc):
    return error_response(str(exc), status_code=422)


@app.exception_handler(Exception)
async def generic_handler(request: Request, exc: Exception):
    # Log the full exception with traceback (server-side only)
    logger.exception("Unhandled exception occurred")
    # Generic message — no stack trace leaked to the client
    return error_response("Internal server error", status_code=500)
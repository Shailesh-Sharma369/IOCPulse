import sys
from pathlib import Path

# Add project root to sys.path to allow importing src/
ROOT_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import logging

from app.config import get_cors_origins
from app.routers import health_router, dashboard_router, articles_raw_router, articles_processed_router
from app.utils.response import error_response
from app.utils.exceptions import NotFoundError, ValidationError

from app.routers.sources import router as sources_router
from app.routers.export import router as export_router

from app.routers.jobs import router as jobs_router
from app.routers.dashboard_analytics import router as dashboard_analytics_router

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="CTI Platform API",
    version="1.0.0",
    description="Backend for Cyber Threat Intelligence Platform – Milestone 1"
)

# CORS middleware – origins read from settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # allow all for testing
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health_router)
app.include_router(dashboard_router)
app.include_router(articles_raw_router)
app.include_router(articles_processed_router)
app.include_router(jobs_router)
app.include_router(sources_router)
app.include_router(export_router)
app.include_router(dashboard_analytics_router)


# Global exception handlers
@app.exception_handler(NotFoundError)
async def not_found_handler(request, exc):
    return error_response(str(exc), status_code=404)

@app.exception_handler(ValidationError)
async def validation_handler(request, exc):
    return error_response(str(exc), status_code=422)

@app.exception_handler(Exception)
async def generic_handler(request: Request, exc: Exception):
    # Log the full exception with traceback
    logger.exception("Unhandled exception occurred")
    return error_response("Internal server error", status_code=500)
# src/core/orchestrator.py
"""
Main pipeline orchestrator.
Calls Module 1 (ingestion) and Module 2 (AI processing) sequentially.
"""
import asyncio
import logging
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.core.config import settings
from src.shared.database import DatabaseClient
from src.module_1_ingestion.source_manager import SourceManager
from src.module_2_llm_processing.processor import ArticleProcessor
from src.module_2_llm_processing.llm_client import LLMClient

logger = logging.getLogger(__name__)

async def run_module_1():
    """Run the ingestion pipeline (existing)."""
    manager = SourceManager()
    count = await manager.ingest_and_persist()
    logger.info(f"Module 1: Ingested {count} new articles.")
    return count

async def run_module_2(limit: int = None):
    """Run the Gemini-based LLM processing pipeline."""
    llm_client = LLMClient(
        api_key=settings.GEMINI_API_KEY,
        model_name=settings.GEMINI_MODEL_NAME,
        fallback_models=settings.gemini_fallback_list,
        timeout=settings.REQUEST_TIMEOUT_SECONDS,
    )
    async with DatabaseClient() as db:
        processor = ArticleProcessor(llm_client, db, batch_size=settings.LLM_BATCH_SIZE)
        count = await processor.run(limit)
        logger.info(f"Module 2: Processed {count} articles.")
        return count

async def run_full_pipeline(ingest_first: bool = True, process_limit: int = None):
    """
    Run the entire pipeline.
    - ingest_first: if True, run Module 1 before Module 2.
    - process_limit: limit the number of articles processed by Module 2.
    """
    if ingest_first:
        await run_module_1()
    await run_module_2(process_limit)

# ---------- CLI entry for testing ----------
if __name__ == "__main__":
    import sys
    # Usage: python -m src.core.orchestrator [--skip-ingest] [--limit N]
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-ingest", action="store_true", help="Skip Module 1")
    parser.add_argument("--limit", type=int, default=None, help="Max articles for Module 2")
    args = parser.parse_args()
    
    asyncio.run(run_full_pipeline(ingest_first=not args.skip_ingest, process_limit=args.limit))
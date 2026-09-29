import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.shared.logging_middleware import setup_logging
from src.core.config import settings
from src.module_1_ingestion.source_manager import SourceManager

async def main():
    setup_logging(settings.LOG_LEVEL)
    manager = SourceManager()
    count = await manager.ingest_and_persist()
    print(f"✅ Ingestion complete. {count} new articles staged.")
    return count

if __name__ == "__main__":
    asyncio.run(main())
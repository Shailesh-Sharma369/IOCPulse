from datetime import datetime, timezone
from dateutil import parser as dateutil_parser
import dateparser
import logging
from typing import Optional
from src.core.exceptions import TemporalFilterError
from src.core.config import settings

logger = logging.getLogger(__name__)

def parse_article_timestamp(timestamp_str: str) -> datetime:
    if not timestamp_str:
        raise TemporalFilterError("Empty timestamp string")
    
    try:
        dt = dateutil_parser.parse(timestamp_str, fuzzy=True)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        pass
    
    try:
        dt = dateparser.parse(timestamp_str, settings={'TIMEZONE': 'UTC', 'RETURN_AS_TIMEZONE_AWARE': True})
        if dt:
            return dt
    except Exception:
        pass
    
    raise TemporalFilterError(f"Could not parse timestamp: {timestamp_str}")

def is_within_date_range(published: Optional[datetime]) -> bool:
    if published is None:
        logger.info("Article has no parsed date – rejecting.")
        return False
    return settings.START_DATE <= published <= settings.END_DATE
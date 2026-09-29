# src/utils/retry.py
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from src.core.exceptions import IngestionError, ParsingError
import logging

logger = logging.getLogger(__name__)

# Used for network calls
retry_network = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((IngestionError, TimeoutError, ConnectionError)),
    before_sleep=lambda retry_state: logger.warning(
        f"Retrying {retry_state.fn.__name__} (attempt {retry_state.attempt_number})"
    )
)

# Used for parsing failures (less aggressive)
retry_parse = retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=0.5, min=1, max=5),
    retry=retry_if_exception_type(ParsingError)
)
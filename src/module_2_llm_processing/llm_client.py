"""
llm_client.py – Async HTTP client for the remote Qwen2.5 inference server.

Changes vs original:
- Retry logic now covers httpx.RemoteProtocolError (server closes connection
  mid-stream, common under heavy GPU load).
- Added explicit connection pool limits to prevent socket exhaustion under
  concurrent batch calls.
- Response validation: warns clearly when the server returns fewer responses
  than requested rather than silently returning a mismatched list.
- Temperature / do_sample consistency: client passes do_sample=False and
  temperature=0.0 by default to match the server's active generation config.
- Added __repr__ for easy debugging.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

import httpx
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)


class LLMClient:
    """
    Thin async client for the /generate endpoint of the CTI LLM inference server.

    Parameters
    ----------
    base_url : str
        Base URL of the inference server (e.g. "https://abc123.ngrok.io").
    timeout : float
        Per-request timeout in seconds.  Default 120 s covers long batches.
    max_retries : int
        Number of retry attempts on transient errors.  Default 3.
    """

    def __init__(
        self,
        base_url: str,
        timeout: float = 120.0,
        max_retries: int = 3,
    ) -> None:
        self.base_url    = base_url.strip().rstrip("/")
        self.timeout     = timeout
        self.max_retries = max_retries

        # Connection pool: cap concurrent connections to avoid exhaustion
        self._limits = httpx.Limits(
            max_keepalive_connections=5,
            max_connections=10,
            keepalive_expiry=30.0,
        )

    def __repr__(self) -> str:
        return f"LLMClient(base_url={self.base_url!r}, timeout={self.timeout})"

    # ------------------------------------------------------------------
    # Core generate method
    # ------------------------------------------------------------------

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((
            httpx.TimeoutException,
            httpx.NetworkError,
            httpx.RemoteProtocolError,   # server closed connection mid-stream
            httpx.HTTPStatusError,
        )),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def generate(
        self,
        messages_batch: List[List[Dict[str, str]]],
        max_new_tokens: int = 1500,
        temperature: float = 0.0,
        top_p: float = 0.95,
        do_sample: bool = False,
    ) -> List[str]:
        """
        Send a batch of conversation histories to the inference server and
        return the generated response strings in the same order.

        Parameters
        ----------
        messages_batch : list of conversation histories
            Each element is a list of {"role": ..., "content": ...} dicts.
        max_new_tokens : int
            Maximum tokens to generate per response.
        temperature : float
            Sampling temperature.  Ignored when do_sample=False.
        top_p : float
            Nucleus sampling probability.  Ignored when do_sample=False.
        do_sample : bool
            If False (default), greedy decoding is used — consistent with
            the server's active_generation_config.

        Returns
        -------
        list of str
            One response string per input conversation.  May be shorter than
            messages_batch if the server returns a mismatched count (caller
            should handle this case).
        """
        if not messages_batch:
            return []

        payload: Dict[str, Any] = {
            "messages_batch": messages_batch,
            "max_new_tokens": max_new_tokens,
            "temperature":    temperature,
            "top_p":          top_p,
            "do_sample":      do_sample,
        }

        async with httpx.AsyncClient(
            timeout=self.timeout,
            limits=self._limits,
        ) as client:
            response = await client.post(
                f"{self.base_url}/generate",
                json=payload,
                headers={"Content-Type": "application/json"},
            )

            # Raise on 5xx so tenacity can retry
            if response.status_code >= 500:
                raise httpx.HTTPStatusError(
                    f"Server error {response.status_code}: {response.text[:200]}",
                    request=response.request,
                    response=response,
                )

            response.raise_for_status()

        data      = response.json()
        responses = data.get("responses", [])

        if len(responses) != len(messages_batch):
            logger.warning(
                "Response count mismatch from server: expected %d, got %d.",
                len(messages_batch),
                len(responses),
            )

        return responses

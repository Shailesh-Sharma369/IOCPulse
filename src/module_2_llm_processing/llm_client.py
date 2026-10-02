"""
llm_client.py – Async client for Google Gemini structured CTI extraction.

Replaces the previous self-hosted Qwen2.5 inference server. Exposes a stable
`generate(messages_batch, ...)` API so `ArticleProcessor` doesn't care which
backend is in use.

Key design points
-----------------
- Uses the official `google-genai` SDK with native JSON-mode output.
- Sends all conversations in a batch concurrently, preserving order.
- Explicitly disables "thinking" for Gemini 2.5+/3.x so max_output_tokens
  is fully available for the JSON payload (thinking models otherwise spend
  part of the budget on hidden reasoning and can return empty text).
- Retries transient errors (5xx / network / timeouts) with exponential
  backoff. Real errors (invalid key, bad model) fail fast — no silent
  fallback to regex.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, List, Optional

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)


class LLMClient:
    """
    Thin async wrapper around Gemini's generate_content.

    Parameters
    ----------
    api_key : str
        Google AI Studio API key. Get one at
        https://aistudio.google.com/apikey
    model_name : str
        Gemini model ID, e.g. "gemini-2.5-flash", "gemini-2.5-flash-lite",
        "gemini-3.1-flash-lite".
    timeout : float
        Soft timeout hint for callers (the SDK enforces its own HTTP timeout).
    max_retries : int
        Retry attempts on transient errors.
    """

    def __init__(
        self,
        api_key: str,
        model_name: str = "gemini-2.5-flash-lite",
        timeout: float = 120.0,
        max_retries: int = 3,
    ) -> None:
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY is not set. Add it to your .env file "
                "(see .env.example)."
            )
        self.api_key = api_key
        self.model_name = model_name
        self.timeout = timeout
        self.max_retries = max_retries

        # The genai Client is thread-safe; async surface lives at .aio.
        self._client = genai.Client(api_key=self.api_key)

    def __repr__(self) -> str:
        return f"LLMClient(model={self.model_name!r})"

    # ------------------------------------------------------------------ #
    # Message → Gemini conversion
    # ------------------------------------------------------------------ #
    @staticmethod
    def _split_messages(
        messages: List[Dict[str, str]],
    ) -> tuple[Optional[str], List[types.Content]]:
        """
        Convert OpenAI-style messages into Gemini's (system_instruction, contents).

        Role mapping:
            "system"    → system_instruction (Gemini only allows one)
            "assistant" → "model"
            "user"      → "user"
        """
        system_instruction: Optional[str] = None
        contents: List[types.Content] = []

        for msg in messages:
            role = (msg.get("role") or "user").lower()
            text = msg.get("content") or ""

            if role == "system":
                # Gemini allows only one system instruction; concatenate any extras.
                system_instruction = (
                    f"{system_instruction}\n\n{text}".strip()
                    if system_instruction
                    else text
                )
                continue

            gemini_role = "model" if role in ("assistant", "model") else "user"
            contents.append(
                types.Content(role=gemini_role, parts=[types.Part(text=text)])
            )

        return system_instruction, contents

    # ------------------------------------------------------------------ #
    # Single-call primitive
    # ------------------------------------------------------------------ #
    async def _generate_one(
        self,
        messages: List[Dict[str, str]],
        max_new_tokens: int,
        temperature: float,
        top_p: float,
    ) -> str:
        system_instruction, contents = self._split_messages(messages)

        # ---- Build GenerateContentConfig ----
        # We always ask Gemini for JSON, because Module 2's only job is
        # structured CTI extraction. The prompt contains the schema; JSON mode
        # guarantees the response is at least *syntactically* valid JSON.
        config_kwargs = {
            "system_instruction": system_instruction,
            "temperature": temperature,
            "top_p": top_p,
            "max_output_tokens": max_new_tokens,
            "response_mime_type": "application/json",
        }

        # ---- Disable thinking (Gemini 2.5+/3.x) ----
        # Thinking models silently consume max_output_tokens on hidden
        # reasoning. For a deterministic extraction task we want all budget
        # to go to the actual JSON payload. Older SDKs lack ThinkingConfig;
        # we skip gracefully if unavailable.
        try:
            config_kwargs["thinking_config"] = types.ThinkingConfig(
                thinking_budget=0
            )
        except (AttributeError, TypeError):
            pass

        config = types.GenerateContentConfig(**config_kwargs)

        # ---- Call with retries ----
        last_exc: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = await self._client.aio.models.generate_content(
                    model=self.model_name,
                    contents=contents,
                    config=config,
                )

                # Surface *why* a response was empty, instead of silently
                # returning "" and letting the caller fall back to regex.
                text = getattr(response, "text", None)
                if not text:
                    finish_reasons = [
                        str(getattr(c, "finish_reason", None))
                        for c in (getattr(response, "candidates", None) or [])
                    ]
                    feedback = getattr(response, "prompt_feedback", None)
                    logger.error(
                        "Gemini returned EMPTY text. model=%s "
                        "finish_reasons=%s prompt_feedback=%s",
                        self.model_name, finish_reasons, feedback,
                    )
                    raise RuntimeError(
                        f"Gemini returned empty text (finish={finish_reasons})"
                    )

                # Success — log size only, never the payload (may contain PII).
                logger.debug(
                    "Gemini OK: model=%s out_chars=%d",
                    self.model_name, len(text),
                )
                return text

            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "Gemini call FAILED (attempt %d/%d) [%s]: %s",
                    attempt, self.max_retries,
                    type(exc).__name__, exc,
                )
                if attempt < self.max_retries:
                    await asyncio.sleep(min(2 ** attempt, 10))

        # Final failure — raise loudly so the caller fails the job, not
        # silently degrades to regex.
        raise RuntimeError(
            f"Gemini generation failed after {self.max_retries} attempts on "
            f"model '{self.model_name}': "
            f"{type(last_exc).__name__}: {last_exc}"
        ) from last_exc

    # ------------------------------------------------------------------ #
    # Public batch API
    # ------------------------------------------------------------------ #
    async def generate(
        self,
        messages_batch: List[List[Dict[str, str]]],
        max_new_tokens: int = 2048,
        temperature: float = 0.0,
        top_p: float = 0.95,
    ) -> List[str]:
        """
        Send each conversation to Gemini concurrently.

        Returns one response string per input conversation, preserving order.
        On a per-item failure, that item is replaced with "" — the caller
        decides whether to fail the whole batch (it should).
        """
        if not messages_batch:
            return []

        tasks = [
            self._generate_one(
                messages=msgs,
                max_new_tokens=max_new_tokens,
                temperature=temperature,
                top_p=top_p,
            )
            for msgs in messages_batch
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        out: List[str] = []
        for idx, res in enumerate(results):
            if isinstance(res, Exception):
                logger.error("Gemini batch item %d failed: %s", idx, res)
                out.append("")
            else:
                out.append(res)
        return out
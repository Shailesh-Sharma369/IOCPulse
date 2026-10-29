"""
llm_client.py – Async client for Google Gemini structured CTI extraction.

Model selection is env-driven:
  - GEMINI_MODEL_NAME      → primary model (REQUIRED — no default)
  - GEMINI_FALLBACK_MODELS → comma-separated fallbacks (OPTIONAL, empty = none)

No model names are hardcoded anywhere. If GEMINI_MODEL_NAME is empty, the
client raises a clear error at construction time — fail-fast, not silent.

Retries transient errors (503/429/timeouts) per model, then moves to the
next fallback model. Non-transient errors (401/403/404) fail immediately.
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
        Primary Gemini model ID (from GEMINI_MODEL_NAME in .env).
        REQUIRED — no default. Empty string raises ValueError.
    timeout : float
        Soft timeout hint for callers (SDK enforces its own HTTP timeout).
    max_retries : int
        Retry attempts per model before moving to the next fallback.
    fallback_models : list[str] | None
        Optional extra models tried if the primary is overloaded (503/429).
        None or [] → no fallbacks (retry only the primary).
    """

    def __init__(
        self,
        api_key: str,
        model_name: str,
        timeout: float = 120.0,
        max_retries: int = 3,
        fallback_models: Optional[List[str]] = None,
    ) -> None:
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY is not set. Add it to your .env file "
                "(see .env.example)."
            )
        if not model_name or not model_name.strip():
            raise ValueError(
                "GEMINI_MODEL_NAME is not set. Add it to your .env file "
                "(e.g. GEMINI_MODEL_NAME=gemini-3.1-flash-lite)."
            )

        self.api_key = api_key
        self.model_name = model_name.strip()
        self.timeout = timeout
        self.max_retries = max_retries
        self._client = genai.Client(api_key=self.api_key)

        # Build the model chain: primary first, then deduped fallbacks.
        self._model_chain: List[str] = [self.model_name] + [
            m for m in (fallback_models or []) if m and m.strip() and m != self.model_name
        ]

    def __repr__(self) -> str:
        return f"LLMClient(primary={self.model_name!r}, chain={self._model_chain!r})"

    # ------------------------------------------------------------------ #
    # Message → Gemini conversion
    # ------------------------------------------------------------------ #
    @staticmethod
    def _split_messages(
        messages: List[Dict[str, str]],
    ) -> tuple[Optional[str], List[types.Content]]:
        """
        Convert OpenAI-style messages into Gemini's
        (system_instruction, contents).

        Role mapping:
            "system"    → system_instruction (Gemini allows only one)
            "assistant" → "model"
            "user"      → "user"
        """
        system_instruction: Optional[str] = None
        contents: List[types.Content] = []

        for msg in messages:
            role = (msg.get("role") or "user").lower()
            text = msg.get("content") or ""

            if role == "system":
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
    # Error classification — decides retry vs. fallback vs. fail-fast
    # ------------------------------------------------------------------ #
    @staticmethod
    def _is_transient(exc: Exception) -> bool:
        """
        Return True if the error is worth retrying (503, 429, timeouts, network).
        Return False for permanent errors (401, 403, 404, invalid request).
        """
        err_str = str(exc)
        transient_markers = (
            "503", "UNAVAILABLE",
            "429", "RESOURCE_EXHAUSTED",
            "500", "INTERNAL",
            "502", "BAD_GATEWAY",
            "504", "DEADLINE_EXCEEDED",
            "Timeout", "timed out",
            "Connection", "ConnectError", "ReadError",
        )
        return any(m in err_str or m in type(exc).__name__ for m in transient_markers)

    # ------------------------------------------------------------------ #
    # Single-call primitive with per-model retry + cross-model fallback
    # ------------------------------------------------------------------ #
    async def _generate_one(
        self,
        messages: List[Dict[str, str]],
        max_new_tokens: int,
        temperature: float,
        top_p: float,
    ) -> str:
        system_instruction, contents = self._split_messages(messages)

        config_kwargs = {
            "system_instruction": system_instruction,
            "temperature": temperature,
            "top_p": top_p,
            "max_output_tokens": max_new_tokens,
            "response_mime_type": "application/json",
        }

        # Disable "thinking" on 2.5+/3.x — otherwise thinking tokens
        # silently consume max_output_tokens and can leave the JSON empty.
        try:
            config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
        except (AttributeError, TypeError):
            pass

        config = types.GenerateContentConfig(**config_kwargs)

        last_exc: Optional[Exception] = None

        for model_idx, model in enumerate(self._model_chain):
            is_fallback = model_idx > 0
            if is_fallback:
                logger.warning(
                    "Primary model %s unavailable — trying fallback model %s",
                    self.model_name, model,
                )

            for attempt in range(1, self.max_retries + 1):
                try:
                    response = await self._client.aio.models.generate_content(
                        model=model,
                        contents=contents,
                        config=config,
                    )

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
                            model, finish_reasons, feedback,
                        )
                        raise RuntimeError(
                            f"Gemini returned empty text (finish={finish_reasons})"
                        )

                    if is_fallback:
                        logger.info(
                            "Gemini OK via fallback model %s (primary %s was unavailable)",
                            model, self.model_name,
                        )
                    else:
                        logger.debug("Gemini OK: model=%s out_chars=%d", model, len(text))
                    return text

                except Exception as exc:
                    last_exc = exc

                    if not self._is_transient(exc):
                        logger.error(
                            "Gemini call failed with non-transient error [%s] "
                            "model=%s: %s",
                            type(exc).__name__, model, exc,
                        )
                        raise

                    logger.warning(
                        "Gemini call FAILED (transient) [%s] model=%s "
                        "attempt %d/%d: %s",
                        type(exc).__name__, model, attempt, self.max_retries, exc,
                    )
                    if attempt < self.max_retries:
                        await asyncio.sleep(min(2 ** attempt, 10))

            if len(self._model_chain) > 1:
                logger.warning(
                    "Model %s exhausted all %d retries — moving to next fallback.",
                    model, self.max_retries,
                )

        tried = " → ".join(self._model_chain)
        raise RuntimeError(
            f"All Gemini models failed ({tried}). "
            f"Last error: {type(last_exc).__name__}: {last_exc}"
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
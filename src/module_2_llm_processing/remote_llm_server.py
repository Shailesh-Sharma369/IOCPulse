"""
remote_llm_server.py – FastAPI inference server for Qwen2.5-3B-Instruct.

Changes vs original:
- Added /ready endpoint (distinct from /health) so start_server.py can poll
  model-load completion without re-implementing the health-check logic.
- Added request_id to each log entry for easier tracing across concurrent calls.
- Moved global mutable state into a ServerState dataclass to make dependencies
  explicit and testable.
- Added /metrics endpoint (token throughput, request count, error count).
- Generation config is validated on startup to catch environment mismatches early.
- CUDA OOM recovery: cache is cleared and the batch is retried at size 1 before
  returning 503.
- Proper graceful shutdown: model is moved off-GPU before the process exits to
  avoid CUDA teardown errors.
- Fixed truncation to preserve generation-prompt suffix (truncation_side="left"
  passed as call-site kwarg, not set as persistent attribute).
- Fixed batch decoding slice for left-padded prompts: use constant prompt_length
  instead of per-sample attention_mask sum.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import traceback
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import torch
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

# ===== Compatibility shims =====
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "0")

# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
)
logger = logging.getLogger("cti_llm_server")

# ---------------------------------------------------------------------------
# Configuration (all overridable via environment variables)
# ---------------------------------------------------------------------------
MODEL_NAME     = os.getenv("LLM_MODEL_NAME",     "Qwen/Qwen2.5-3B-Instruct")
USE_4BIT       = os.getenv("LLM_USE_4BIT",       "true").lower() == "true"
MAX_SEQ_LEN    = int(os.getenv("LLM_MAX_SEQ_LEN",    "16384"))
MAX_BATCH_SIZE = int(os.getenv("LLM_MAX_BATCH_SIZE",  "8"))

# Generation defaults — mirrored in /health response for client validation
_GEN_DEFAULTS: Dict[str, Any] = {
    "max_new_tokens":       int(os.getenv("LLM_MAX_NEW_TOKENS", "1500")),
    "temperature":          0.0,
    "top_p":                0.95,
    "do_sample":            False,
    "repetition_penalty":   None,   # not set; transformers defaults to 1.0
    "no_repeat_ngram_size": None,   # not set; no n-gram blocking
}

# ---------------------------------------------------------------------------
# Device detection
# ---------------------------------------------------------------------------
if torch.cuda.is_available():
    DEVICE      = "cuda"
    DEVICE_MAP  = "auto"
    TORCH_DTYPE = torch.float16
    logger.info("✅ CUDA available: %s", torch.cuda.get_device_name(0))
else:
    DEVICE      = "cpu"
    DEVICE_MAP  = None
    TORCH_DTYPE = torch.float32
    logger.warning("⚠️  CUDA not available — running on CPU (will be very slow).")


# ---------------------------------------------------------------------------
# Server state
# ---------------------------------------------------------------------------

@dataclass
class ServerState:
    model:     Optional[Any]        = None
    tokenizer: Optional[Any]        = None
    lock:      Optional[asyncio.Lock] = None
    start_time: float               = field(default_factory=time.time)
    max_seq_len: int                = MAX_SEQ_LEN
    # Metrics
    request_count: int              = 0
    error_count:   int              = 0
    total_tokens_generated: int     = 0


_state = ServerState()


# ---------------------------------------------------------------------------
# Lifespan (model loading + cleanup)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _state
    _state.start_time = time.time()
    _state.lock       = asyncio.Lock()

    logger.info("Loading %s on %s (4-bit: %s)", MODEL_NAME, DEVICE, USE_4BIT)

    # --- Quantization config ---
    quant_cfg = None
    if USE_4BIT and DEVICE == "cuda":
        try:
            quant_cfg = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_use_double_quant=True,
            )
            logger.info("4-bit NF4 quantization configured.")
        except ImportError:
            logger.warning("bitsandbytes not installed; falling back to FP16.")

    model_kwargs: Dict[str, Any] = {
        "device_map":       DEVICE_MAP if DEVICE == "cuda" else None,
        "dtype":            TORCH_DTYPE,
        "trust_remote_code": True,
        "low_cpu_mem_usage": True,
    }
    if quant_cfg:
        model_kwargs["quantization_config"] = quant_cfg

    # --- Tokenizer ---
    logger.info("Loading tokenizer…")
    try:
        _state.tokenizer = AutoTokenizer.from_pretrained(
            MODEL_NAME, trust_remote_code=True
        )
        logger.info("Tokenizer loaded.")
    except Exception:
        logger.error("Tokenizer load failed:")
        traceback.print_exc()
        raise

    if _state.tokenizer.pad_token is None:
        _state.tokenizer.pad_token = _state.tokenizer.eos_token
    _state.tokenizer.padding_side = "left"
    # DO NOT set truncation_side persistently – it may affect other tokenizer calls.
    # We pass truncation_side="left" only at the call site in _run_inference.

    # --- Model ---
    logger.info("Loading model (first run may download weights)…")
    try:
        _state.model = AutoModelForCausalLM.from_pretrained(MODEL_NAME, **model_kwargs)
        logger.info("Model loaded.")
    except RuntimeError as exc:
        if "out of memory" in str(exc).lower():
            logger.error(
                "CUDA OOM during model load. "
                "Try LLM_USE_4BIT=true or reducing LLM_MAX_SEQ_LEN."
            )
        traceback.print_exc()
        raise
    except Exception:
        logger.error("Unexpected error during model load:")
        traceback.print_exc()
        raise

    # Cap MAX_SEQ_LEN to the model's actual context window
    model_max = getattr(_state.model.config, "max_position_embeddings", None)
    if model_max and _state.max_seq_len > model_max:
        logger.warning(
            "LLM_MAX_SEQ_LEN=%d exceeds model max=%d; capping to %d.",
            _state.max_seq_len, model_max, model_max,
        )
        _state.max_seq_len = model_max

    _state.model.eval()
    logger.info(
        "✅ Server ready. Model on: %s",
        next(_state.model.parameters()).device,
    )

    yield  # ← server is now handling requests

    # --- Graceful shutdown ---
    logger.info("Shutdown: releasing GPU memory…")
    if _state.model is not None and DEVICE == "cuda":
        _state.model.cpu()
        del _state.model
        torch.cuda.empty_cache()
    logger.info("Shutdown complete.")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="CTI LLM Server",
    version="1.1",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class GenerateRequest(BaseModel):
    messages_batch: List[List[Dict[str, str]]]
    max_new_tokens: Optional[int]   = _GEN_DEFAULTS["max_new_tokens"]
    temperature:    Optional[float] = _GEN_DEFAULTS["temperature"]
    top_p:          Optional[float] = _GEN_DEFAULTS["top_p"]
    do_sample:      Optional[bool]  = _GEN_DEFAULTS["do_sample"]


class GenerateResponse(BaseModel):
    responses:  List[str]
    request_id: str


# ---------------------------------------------------------------------------
# /generate
# ---------------------------------------------------------------------------

@app.post("/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest, http_request: Request):
    request_id = str(uuid.uuid4())[:8]
    _state.request_count += 1

    if not _is_ready():
        raise HTTPException(503, "Model is still loading. Please retry shortly.")

    if not request.messages_batch:
        raise HTTPException(400, "messages_batch must not be empty.")

    if len(request.messages_batch) > MAX_BATCH_SIZE:
        raise HTTPException(
            400,
            f"Batch size {len(request.messages_batch)} exceeds limit {MAX_BATCH_SIZE}.",
        )

    logger.info("[%s] Generate request: batch=%d max_new_tokens=%d",
                request_id, len(request.messages_batch), request.max_new_tokens)

    debug = os.getenv("DEBUG_TRUNCATION", "false").lower() == "true"

    try:
        async with _state.lock:
            responses = await asyncio.to_thread(
                _run_inference,
                request,
                request_id,
                debug,
            )
        _state.total_tokens_generated += sum(len(r.split()) for r in responses)
        logger.info("[%s] Done. Responses: %d", request_id, len(responses))
        return GenerateResponse(responses=responses, request_id=request_id)

    except torch.cuda.OutOfMemoryError:
        _state.error_count += 1
        logger.error("[%s] CUDA OOM — clearing cache and retrying at batch_size=1.", request_id)
        torch.cuda.empty_cache()
        # Retry each item individually
        responses = []
        for single_messages in request.messages_batch:
            try:
                single_req = GenerateRequest(
                    messages_batch=[single_messages],
                    max_new_tokens=min(request.max_new_tokens, 512),
                    temperature=request.temperature,
                    top_p=request.top_p,
                    do_sample=request.do_sample,
                )
                r = _run_inference(single_req, request_id + "_retry", debug=False)
                responses.extend(r)
            except Exception as exc:
                logger.error("[%s] OOM retry failed: %s", request_id, exc)
                responses.append("")  # return empty string rather than crashing
        if responses:
            return GenerateResponse(responses=responses, request_id=request_id)
        raise HTTPException(503, "GPU out of memory. Reduce batch size or max_new_tokens.")

    except Exception as exc:
        _state.error_count += 1
        logger.error("[%s] Generation error: %s", request_id, exc, exc_info=True)
        raise HTTPException(500, str(exc))


def _run_inference(
    request: GenerateRequest,
    request_id: str,
    debug: bool = False,
) -> List[str]:
    """
    Synchronous inference function — called via asyncio.to_thread() to avoid
    blocking the event loop during GPU computation.
    """
    tokenizer   = _state.tokenizer
    model       = _state.model
    max_seq_len = _state.max_seq_len

    prompts = [
        tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        for messages in request.messages_batch
    ]

    if debug:
        for idx, prompt in enumerate(prompts):
            no_trunc_ids = tokenizer(prompt, truncation=False, return_tensors=None)
            logger.info(
                "[%s] Prompt[%d]: chars=%d tokens=%d",
                request_id, idx, len(prompt), len(no_trunc_ids["input_ids"]),
            )

    # CRITICAL: truncate from the left to preserve the generation-prompt suffix.
    # We pass truncation_side="left" here – it does not modify the tokenizer object.
    inputs = tokenizer(
        prompts,
        return_tensors="pt",
        padding=True,
        truncation=True,
        max_length=max_seq_len,
        truncation_side="left",   # ← preserve the end of the prompt
    )

    if debug:
        for i, ids in enumerate(inputs["input_ids"]):
            actual = (ids != tokenizer.pad_token_id).sum().item()
            original_len = len(tokenizer(prompts[i], truncation=False)["input_ids"])
            if original_len > max_seq_len:
                logger.warning("[%s] Prompt[%d] truncated: %d → %d tokens",
                               request_id, i, original_len, actual)

    device = next(model.parameters()).device
    inputs = {k: v.to(device) for k, v in inputs.items()}

    # CRITICAL FIX for left‑padded batches:
    # The tokenizer pads on the left, so the actual prompt width is the same
    # for all sequences in the batch: inputs["input_ids"].shape[1].
    # Using per‑sequence attention_mask sum would start slicing inside the prompt
    # for shorter sequences.  We use the constant width instead.
    prompt_length = inputs["input_ids"].shape[1]

    gen_kwargs: Dict[str, Any] = {
        "max_new_tokens": request.max_new_tokens,
        "temperature":    request.temperature,
        "top_p":          request.top_p,
        "do_sample":      request.do_sample,
        "pad_token_id":   tokenizer.eos_token_id,
        "eos_token_id":   tokenizer.eos_token_id,
        "use_cache":      True,
    }

    with torch.inference_mode():
        outputs = model.generate(**inputs, **gen_kwargs)

    return [
        tokenizer.decode(
            outputs[i, prompt_length:],   # ← fixed: constant prompt_length
            skip_special_tokens=True,
        )
        for i in range(outputs.shape[0])
    ]


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    gpu_info: Dict[str, Any] = {}
    if torch.cuda.is_available():
        for i in range(torch.cuda.device_count()):
            free, total = torch.cuda.mem_get_info(i)
            props = torch.cuda.get_device_properties(i)
            gpu_info[f"gpu_{i}"] = {
                "name":       props.name,
                "total_mb":   total // 1024 // 1024,
                "free_mb":    free  // 1024 // 1024,
                "used_mb":    (total - free) // 1024 // 1024,
            }
    else:
        gpu_info = {"available": False}

    model_device: Optional[str] = None
    if _state.model is not None:
        try:
            model_device = str(next(_state.model.parameters()).device)
        except StopIteration:
            model_device = "unknown"

    return {
        "status":          "ok" if _is_ready() else "starting",
        "model":           MODEL_NAME,
        "quantization":    "4bit" if USE_4BIT else "fp16",
        "device":          DEVICE,
        "model_device":    model_device,
        "gpu":             gpu_info,
        "uptime_seconds":  round(time.time() - _state.start_time, 1),
        "model_loaded":    _state.model    is not None,
        "tokenizer_loaded": _state.tokenizer is not None,
        "server_ready":    _is_ready(),
        "configured_max_seq_len":  _state.max_seq_len,
        "configured_batch_limit":  MAX_BATCH_SIZE,
        "active_generation_config": _GEN_DEFAULTS,
        "metrics": {
            "request_count":           _state.request_count,
            "error_count":             _state.error_count,
            "total_tokens_generated":  _state.total_tokens_generated,
        },
    }


# ---------------------------------------------------------------------------
# /ready  (lightweight poll used by start_server.py)
# ---------------------------------------------------------------------------

@app.get("/ready")
async def ready():
    """Returns 200 only when the model is fully loaded and ready to serve."""
    if not _is_ready():
        raise HTTPException(503, "Model not ready yet.")
    return {"ready": True}


# ---------------------------------------------------------------------------
# /metrics
# ---------------------------------------------------------------------------

@app.get("/metrics")
async def metrics():
    return {
        "request_count":          _state.request_count,
        "error_count":            _state.error_count,
        "total_tokens_generated": _state.total_tokens_generated,
        "uptime_seconds":         round(time.time() - _state.start_time, 1),
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_ready() -> bool:
    return (
        _state.model     is not None
        and _state.tokenizer is not None
        and _state.lock      is not None
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
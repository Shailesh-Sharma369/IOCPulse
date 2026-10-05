"""
Thin re-export shim.

The canonical implementation lives in src/utils/cve_api.py so the
standalone Module 2 pipeline (`python -m src.module_2_llm_processing.processor`)
can import it without depending on the backend package.

This shim lets backend code keep importing from app.utils.cve_api.
"""
import sys
from pathlib import Path

# Ensure the repo root is importable so `src.utils.cve_api` resolves.
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.utils.cve_api import fetch_cve_details  # noqa: F401,E402

__all__ = ["fetch_cve_details"]
"""
cve_api.py – Async CVE enrichment via the NVD REST API v2.0.

Canonical location for the pipeline. `backend/app/utils/cve_api.py` is a
re-export shim so backend imports keep working.

Design guarantees
-----------------
- Never raises: all network / parse errors are caught and logged at DEBUG.
  Failed CVEs are stored as empty dicts so the caller can always iterate
  the result without a KeyError.
- Rate-limit aware: NVD enforces 5 req/30 s without an API key and 50 req/30 s
  with one. We serialize requests and sleep between calls accordingly.
- In-process cache: identical CVEs are not re-fetched across articles.
- Hard cap on batch size: refuses to make more than _MAX_CVES requests.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)


# ----- Constants ------------------------------------------------------------
NVD_BASE_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"

_RATE_LIMIT_NO_KEY   = 6.0     # 5 req / 30 s
_RATE_LIMIT_WITH_KEY = 0.7     # 50 req / 30 s

_MAX_CVES_PER_BATCH = 50
_REQUEST_TIMEOUT_SECONDS = 20

_CACHE: Dict[str, dict] = {}
_CACHE_MAX = 500


# ----- Helpers --------------------------------------------------------------
def _score_to_severity(score) -> Optional[str]:
    if score is None:
        return None
    try:
        s = float(score)
    except (TypeError, ValueError):
        return None
    if s >= 9.0:  return "CRITICAL"
    if s >= 7.0:  return "HIGH"
    if s >= 4.0:  return "MEDIUM"
    if s > 0.0:   return "LOW"
    return "NONE"


def _parse_nvd_payload(cve_id: str, payload: dict) -> dict:
    vulns = payload.get("vulnerabilities") or []
    if not vulns:
        return {}
    cve = vulns[0].get("cve") or {}

    description = ""
    for d in (cve.get("descriptions") or []):
        if d.get("lang") == "en":
            description = (d.get("value") or "").strip()
            break

    metrics = cve.get("metrics") or {}
    score = severity = vector = None
    for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        entries = metrics.get(key) or []
        if not entries:
            continue
        cvss_data = entries[0].get("cvssData") or {}
        score    = cvss_data.get("baseScore")
        vector   = cvss_data.get("vectorString")
        severity = cvss_data.get("baseSeverity") or entries[0].get("baseSeverity")
        if score is not None:
            break

    return {
        "cve_id":        cve.get("id", cve_id),
        "cvss_score":    float(score) if score is not None else None,
        "cvss_severity": severity or _score_to_severity(score),
        "cvss_vector":   vector,
        "description":   description,
        "published":     cve.get("published"),
        "last_modified": cve.get("lastModified"),
        "source":        "NVD",
    }


# ----- Single-CVE fetch -----------------------------------------------------
async def _fetch_one(
    session: aiohttp.ClientSession,
    cve_id: str,
    api_key: str,
) -> dict:
    headers = {"User-Agent": "IOC-Pulse/1.0 (CTI enrichment)"}
    if api_key:
        headers["apiKey"] = api_key

    try:
        async with session.get(
            NVD_BASE_URL,
            params={"cveId": cve_id},
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT_SECONDS),
        ) as resp:
            if resp.status == 404:
                logger.debug("NVD 404 for %s", cve_id)
                return {}
            if resp.status == 403:
                logger.warning(
                    "NVD 403 for %s — check NVD_API_KEY (may be rate-limited)", cve_id,
                )
                return {}
            if resp.status == 429:
                logger.warning("NVD 429 (rate-limited) while fetching %s", cve_id)
                return {}
            if resp.status != 200:
                logger.debug("NVD non-200 (%s) for %s", resp.status, cve_id)
                return {}
            try:
                payload = await resp.json()
            except Exception as exc:
                logger.debug("NVD JSON decode failed for %s: %s", cve_id, exc)
                return {}
        return _parse_nvd_payload(cve_id, payload)
    except asyncio.TimeoutError:
        logger.debug("NVD timeout for %s", cve_id)
        return {}
    except aiohttp.ClientError as exc:
        logger.debug("NVD network error for %s: %s", cve_id, exc)
        return {}
    except Exception as exc:
        logger.debug("NVD unexpected error for %s: %s", cve_id, exc)
        return {}


# ----- Public entry point ---------------------------------------------------
async def fetch_cve_details(cve_list: List[str]) -> Dict[str, dict]:
    """
    Enrich a list of CVE IDs with CVSS score and description from NVD v2.0.

    Never raises. Missing CVEs are returned as empty dicts.
    """
    if not cve_list:
        return {}

    normalized: List[str] = []
    seen: set = set()
    for c in cve_list:
        if not c:
            continue
        cid = str(c).strip().upper()
        if not cid.startswith("CVE-"):
            continue
        if cid in seen:
            continue
        seen.add(cid)
        normalized.append(cid)

    if not normalized:
        return {}

    if len(normalized) > _MAX_CVES_PER_BATCH:
        logger.info(
            "CVE enrichment capped at %d (received %d)",
            _MAX_CVES_PER_BATCH, len(normalized),
        )
        normalized = normalized[:_MAX_CVES_PER_BATCH]

    result: Dict[str, dict] = {}
    to_fetch: List[str] = []
    for cid in normalized:
        if cid in _CACHE:
            result[cid] = _CACHE[cid]
        else:
            to_fetch.append(cid)

    if not to_fetch:
        logger.debug("CVE enrichment: all %d served from cache", len(normalized))
        return result

    try:
        from src.core.config import settings as _settings
        api_key = (_settings.NVD_API_KEY or "").strip()
    except Exception:
        api_key = ""

    delay = _RATE_LIMIT_WITH_KEY if api_key else _RATE_LIMIT_NO_KEY

    logger.info(
        "CVE enrichment: fetching %d CVEs via NVD (%s, %.1fs delay, %d cached)",
        len(to_fetch),
        "authenticated" if api_key else "unauthenticated",
        delay,
        len(result),
    )
    if not api_key and len(to_fetch) > 5:
        logger.warning(
            "NVD_API_KEY not set and %d CVEs to fetch — this will take ~%.0f s. "
            "Get a free key at https://nvd.nist.gov/developers/request-an-api-key",
            len(to_fetch), len(to_fetch) * delay,
        )

    try:
        async with aiohttp.ClientSession() as session:
            for idx, cid in enumerate(to_fetch):
                payload = await _fetch_one(session, cid, api_key)
                result[cid] = payload
                _CACHE[cid] = payload
                if idx < len(to_fetch) - 1:
                    await asyncio.sleep(delay)
    except Exception as exc:
        logger.warning("CVE enrichment session error: %s", exc)
        for cid in to_fetch:
            result.setdefault(cid, {})

    if len(_CACHE) > _CACHE_MAX:
        _CACHE.clear()

    for cid in normalized:
        result.setdefault(cid, {})

    succeeded = sum(1 for cid in normalized if result.get(cid))
    logger.info(
        "CVE enrichment: %d/%d succeeded (%d total in result)",
        succeeded, len(normalized), len(result),
    )
    return result
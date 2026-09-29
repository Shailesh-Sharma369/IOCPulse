"""
verification.py – Post-extraction confidence scoring for Module 2.

Verifies every extracted IOC and metadata value against the original
article text using fuzzy substring matching.  Missing fields are not
penalised; only extracted-but-unverifiable values count against the score.

Key changes:
- All metadata fields are List[str] – verification now iterates over list elements.
- metadata_verification returns per‑item List[bool] (not a single bool per field).
- Added target_organization to metadata fields.
"""

from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.module_2_llm_processing.models import IOCCollection, ProcessedArticle, ThreatMetadata

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class VerificationResult:
    confidence_score:      int
    verification_status:   str   # "verified" | "partial" | "low"
    hallucination_count:   int
    evidence:              Dict[str, str]                      = field(default_factory=dict)
    ioc_verification:      Dict[str, List[bool]]               = field(default_factory=dict)
    metadata_verification: Dict[str, List[bool]]               = field(default_factory=dict)  # per‑item booleans
    mitre_valid:           List[bool]                          = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fuzzy_in_text(value: str, text_lower: str) -> bool:
    """Case-insensitive substring check."""
    if not value:
        return False
    return value.lower() in text_lower


def _extract_evidence(value: str, sentences: List[str]) -> str:
    """Return the first sentence that contains `value` (case-insensitive)."""
    v_lower = value.lower()
    for sent in sentences:
        if v_lower in sent.lower():
            return sent.strip()
    return ""


def _split_sentences(text: str) -> List[str]:
    """Split text into sentences on .!? followed by whitespace."""
    return re.split(r'(?<=[.!?])\s+', text)


# ---------------------------------------------------------------------------
# Main verification function
# ---------------------------------------------------------------------------

def verify_article(article_text: str, parsed: ProcessedArticle) -> VerificationResult:
    """
    Verify extracted entities against the source article text.

    Scoring:
      - For each extracted value, check if it appears verbatim (case-insensitive)
        in the article.
      - confidence_score = verified / total_extracted * 100
      - hallucination_count = total_extracted - verified
      - Missing fields (empty lists) are not extracted → not scored.

    Returns a VerificationResult.  If nothing was extracted, returns
    confidence_score=50 (insufficient data to judge).
    """
    article_text = html.unescape(article_text or "")
    text_lower   = article_text.lower()
    sentences    = _split_sentences(article_text)

    evidence:              Dict[str, str]                      = {}
    ioc_verification:      Dict[str, List[bool]]               = {}
    metadata_verification: Dict[str, List[bool]]               = {}
    mitre_valid:           List[bool]                          = []

    total_extracted   = 0
    verified_count    = 0

    # ---- IOC verification ----
    iocs = parsed.iocs
    for field_name in IOCCollection.__fields__:
        values: List[str] = getattr(iocs, field_name, [])
        field_results: List[bool] = []
        for val in values:
            if not val:
                continue
            total_extracted += 1
            found = _fuzzy_in_text(val, text_lower)
            field_results.append(found)
            if found:
                verified_count += 1
                ev_key = f"ioc_{field_name}_{val}"
                if ev_key not in evidence:
                    evidence[ev_key] = _extract_evidence(val, sentences)
        ioc_verification[field_name] = field_results

    # ---- Metadata verification ----
    # All metadata fields are List[str] — iterate over each element.
    meta = parsed.threat_metadata
    _META_FIELDS = [
        "threat_actor", "malware_name", "attack_type", "target_organization",
        "target_industry", "target_country", "campaign_name",
        "ransomware_family", "affected_software",
    ]
    for field_name in _META_FIELDS:
        values = getattr(meta, field_name, [])
        field_results: List[bool] = []
        if not values:
            metadata_verification[field_name] = []
            continue
        for val in values:
            if not val:
                field_results.append(False)
                continue
            total_extracted += 1
            found = _fuzzy_in_text(val, text_lower)
            field_results.append(found)
            if found:
                verified_count += 1
                ev_key = f"meta_{field_name}"
                if ev_key not in evidence:
                    evidence[ev_key] = _extract_evidence(val, sentences)
        metadata_verification[field_name] = field_results

    # ---- MITRE technique verification ----
    _MITRE_RE = re.compile(r'^T\d{4}(?:\.\d{1,3})?$')
    for tech in meta.mitre_techniques:
        if not tech:
            continue
        total_extracted += 1
        # Validate format (must be Tdddd or Tdddd.ddd)
        valid_format = bool(_MITRE_RE.match(tech.upper()))
        found_in_text = _fuzzy_in_text(tech, text_lower)
        is_verified = valid_format and found_in_text
        mitre_valid.append(is_verified)
        if is_verified:
            verified_count += 1
            ev_key = f"mitre_{tech}"
            if ev_key not in evidence:
                evidence[ev_key] = _extract_evidence(tech, sentences)

    # ---- Confidence score ----
    if total_extracted == 0:
        # Nothing extracted → insufficient data; score 50 (neutral)
        confidence_score = 50
    else:
        confidence_score = int((verified_count / total_extracted) * 100)

    hallucination_count = total_extracted - verified_count

    if confidence_score >= 80:
        status = "verified"
    elif confidence_score >= 50:
        status = "partial"
    else:
        status = "low"

    logger.debug(
        "Verification: score=%d status=%s verified=%d/%d hallucinations=%d",
        confidence_score, status, verified_count, total_extracted, hallucination_count,
    )

    return VerificationResult(
        confidence_score=confidence_score,
        verification_status=status,
        hallucination_count=hallucination_count,
        evidence=evidence,
        ioc_verification=ioc_verification,
        metadata_verification=metadata_verification,
        mitre_valid=mitre_valid,
    )
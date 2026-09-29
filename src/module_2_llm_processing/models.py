"""
models.py – Pydantic data models for Module 2 CTI extraction output.

Design notes:
- All list fields use a pre-validator (_coerce_list) to robustly handle
  every scalar/None/set/tuple variant the LLM might produce.
- ProcessedArticle.from_json() is removed (dead code in original); parsing
  is now wholly owned by ArticleProcessor._attempt_parse() which has richer
  error recovery.
- Config.extra = "ignore" on all models: unknown LLM-invented fields
  (e.g. "firefox_extension", "thor_attack") are silently discarded rather
  than raising or polluting the model.
- Added summary (string) and target_organization (list) per SOC analyst requirements.
"""

from __future__ import annotations

from typing import Any, List

from pydantic import BaseModel, Field, validator


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _coerce_list(value: Any) -> List[str]:
    """
    Coerce any value into a deduplicated List[str].
    Handles: None, scalar, list, tuple, set.
    Filters out: None elements, empty strings, and placeholder nulls
    like "none", "null", "n/a", "unknown".
    """
    _NULL_VALUES = frozenset({"none", "null", "n/a", "unknown", "not applicable", ""})

    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        items: list = list(value)
    elif isinstance(value, set):
        items = sorted(value)  # deterministic order for sets
    else:
        items = [value]

    seen: set = set()
    result: List[str] = []
    for item in items:
        if item is None:
            continue
        text = str(item).strip()
        if not text or text.lower() in _NULL_VALUES:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


# ---------------------------------------------------------------------------
# IOC collection
# ---------------------------------------------------------------------------

class IOCCollection(BaseModel):
    """
    Indicators of Compromise extracted from a CTI article.
    All fields are lists of strings.  Unknown fields are ignored.
    """
    ip:           List[str] = Field(default_factory=list)
    domain:       List[str] = Field(default_factory=list)
    url:          List[str] = Field(default_factory=list)
    md5:          List[str] = Field(default_factory=list)
    sha1:         List[str] = Field(default_factory=list)
    sha256:       List[str] = Field(default_factory=list)
    cve:          List[str] = Field(default_factory=list)
    email:        List[str] = Field(default_factory=list)
    file_name:    List[str] = Field(default_factory=list)
    registry_key: List[str] = Field(default_factory=list)
    mutex:        List[str] = Field(default_factory=list)
    malware_family: List[str] = Field(default_factory=list)

    @validator(
        "ip", "domain", "url", "md5", "sha1", "sha256", "cve", "email",
        "file_name", "registry_key", "mutex", "malware_family",
        pre=True, always=True,
    )
    def coerce_list_fields(cls, v: Any) -> List[str]:
        return _coerce_list(v)

    class Config:
        extra = "ignore"  # silently discard LLM-invented fields


# ---------------------------------------------------------------------------
# Threat metadata
# ---------------------------------------------------------------------------

class ThreatMetadata(BaseModel):
    """
    Contextual threat intelligence metadata extracted from a CTI article.
    All fields are lists of strings.  Unknown fields are ignored.
    """
    threat_actor:      List[str] = Field(default_factory=list)
    malware_name:      List[str] = Field(default_factory=list)
    attack_type:       List[str] = Field(default_factory=list)
    target_organization: List[str] = Field(default_factory=list)   # NEW
    target_industry:   List[str] = Field(default_factory=list)
    target_country:    List[str] = Field(default_factory=list)
    mitre_techniques:  List[str] = Field(default_factory=list)
    affected_software: List[str] = Field(default_factory=list)
    campaign_name:     List[str] = Field(default_factory=list)
    ransomware_family: List[str] = Field(default_factory=list)

    @validator(
        "threat_actor", "malware_name", "attack_type", "target_organization",
        "target_industry", "target_country", "mitre_techniques",
        "affected_software", "campaign_name", "ransomware_family",
        pre=True, always=True,
    )
    def coerce_list_fields(cls, v: Any) -> List[str]:
        return _coerce_list(v)

    class Config:
        extra = "ignore"


# ---------------------------------------------------------------------------
# Processed article (top-level output model)
# ---------------------------------------------------------------------------

class ProcessedArticle(BaseModel):
    """
    Complete output of Module 2 for a single article.
    """
    summary:          str            = ""   # NEW – short technical summary
    iocs:             IOCCollection  = Field(default_factory=IOCCollection)
    threat_metadata:  ThreatMetadata = Field(default_factory=ThreatMetadata)

    class Config:
        extra = "ignore"
"""
models.py – Pydantic data models for Module 2 CTI extraction output.

- All list fields use a pre-validator (_coerce_list) to handle every
  scalar/None/set/tuple variant the LLM might produce.
- Config.extra = "ignore" on all models: unknown LLM-invented fields are
  silently discarded rather than polluting the model.
- severity / tlp_tag have tolerant normalizers so the pipeline never crashes
  on casing / list-wrapping / separator variations.
- cve_details is populated programmatically by CVE enrichment (NVD), never
  by the LLM.
"""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field, validator


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _coerce_list(value: Any) -> List[str]:
    """
    Coerce any value into a deduplicated List[str].
    Handles: None, scalar, list, tuple, set.
    Filters out: None elements, empty strings, placeholder nulls.
    """
    _NULL_VALUES = frozenset({"none", "null", "n/a", "unknown", "not applicable", ""})

    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        items: list = list(value)
    elif isinstance(value, set):
        items = sorted(value)
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
# Severity / TLP canonical sets
# ---------------------------------------------------------------------------

_VALID_SEVERITIES_LOWER = ("critical", "high", "medium", "low")
_TLP_LEVELS = frozenset({"CLEAR", "GREEN", "AMBER", "RED"})


# ---------------------------------------------------------------------------
# IOC collection
# ---------------------------------------------------------------------------

class IOCCollection(BaseModel):
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
        extra = "ignore"


# ---------------------------------------------------------------------------
# Threat metadata
# ---------------------------------------------------------------------------

class ThreatMetadata(BaseModel):
    threat_actor:        List[str] = Field(default_factory=list)
    malware_name:        List[str] = Field(default_factory=list)
    attack_type:         List[str] = Field(default_factory=list)
    target_organization: List[str] = Field(default_factory=list)
    target_industry:     List[str] = Field(default_factory=list)
    target_country:      List[str] = Field(default_factory=list)
    mitre_techniques:    List[str] = Field(default_factory=list)
    affected_software:   List[str] = Field(default_factory=list)
    campaign_name:       List[str] = Field(default_factory=list)
    ransomware_family:   List[str] = Field(default_factory=list)

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
    summary:         str             = ""
    severity:        str             = "Unknown"       # Low | Medium | High | Critical | Unknown
    tlp_tag:         str             = "TLP:CLEAR"     # TLP:CLEAR | TLP:GREEN | TLP:AMBER | TLP:RED
    cve_details:     Dict[str, Any]  = Field(default_factory=dict)   # NVD enrichment
    iocs:            IOCCollection   = Field(default_factory=IOCCollection)
    threat_metadata: ThreatMetadata  = Field(default_factory=ThreatMetadata)

    # ------------------------------------------------------------------ #
    # Severity normalizer
    # ------------------------------------------------------------------ #
    @validator("severity", pre=True, always=True)
    def _normalize_severity(cls, v: Any) -> str:
        if v is None:
            return "Unknown"
        if isinstance(v, list):
            v = v[0] if v else "Unknown"
        s = str(v).strip()
        if not s:
            return "Unknown"
        low = s.lower()
        for level in _VALID_SEVERITIES_LOWER:
            if low == level:
                return level.capitalize()
        for level in _VALID_SEVERITIES_LOWER:  # partial match fallback
            if level in low:
                return level.capitalize()
        return "Unknown"

    # ------------------------------------------------------------------ #
    # TLP tag normalizer
    # ------------------------------------------------------------------ #
    @validator("tlp_tag", pre=True, always=True)
    def _normalize_tlp(cls, v: Any) -> str:
        if v is None:
            return "TLP:CLEAR"
        if isinstance(v, list):
            v = v[0] if v else "TLP:CLEAR"
        s = str(v).strip().upper()
        if not s:
            return "TLP:CLEAR"

        # Normalize separators
        s = s.replace("-", ":").replace(" ", ":").replace("_", ":")
        while "::" in s:
            s = s.replace("::", ":")

        if not s.startswith("TLP:"):
            s = "TLP:" + s.lstrip(":")

        parts = s.split(":", 1)
        level = (parts[1] if len(parts) > 1 else "").split("+")[0].strip()

        if level in _TLP_LEVELS:
            return f"TLP:{level}"
        return "TLP:CLEAR"  # fail open on ambiguity

    class Config:
        extra = "ignore"
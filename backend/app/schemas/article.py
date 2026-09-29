from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

# --- IOC & Threat Metadata sub-schemas ---

class IOCCollectionResponse(BaseModel):
    ip: List[str] = []
    domain: List[str] = []
    url: List[str] = []
    md5: List[str] = []
    sha1: List[str] = []
    sha256: List[str] = []
    cve: List[str] = []
    email: List[str] = []
    file_name: List[str] = []
    registry_key: List[str] = []
    mutex: List[str] = []
    malware_family: List[str] = []

class ThreatMetadataResponse(BaseModel):
    threat_actor: List[str] = []
    malware_name: List[str] = []
    attack_type: List[str] = []
    target_organization: List[str] = []
    target_industry: List[str] = []
    target_country: List[str] = []
    mitre_techniques: List[str] = []
    affected_software: List[str] = []
    campaign_name: List[str] = []
    ransomware_family: List[str] = []

# --- Raw Article ---

class RawArticleResponse(BaseModel):
    id: int
    metadata_hash: str
    source_domain: str
    source_url: str
    title: Optional[str]
    author: Optional[str]
    published_utc: Optional[datetime]
    raw_html: Optional[str]          # may be truncated in list view
    original_source_url: Optional[str]
    source_status: str               # MIRROR / ORIGINAL
    retrieved_utc: datetime
    status: str                      # PENDING / PROCESSED / FAILED
    processing_error: Optional[str]

# --- Processed Article (joined with raw) ---

class ProcessedArticleResponse(BaseModel):
    # from staging_raw
    id: int                     # raw article id
    metadata_hash: str
    source_domain: str
    source_url: str
    title: Optional[str]
    author: Optional[str]
    published_utc: Optional[datetime]
    original_source_url: Optional[str]
    source_status: str
    retrieved_utc: datetime
    status: str                 # raw status
    processing_error: Optional[str]

    # from processed_articles
    summary: Optional[str]
    iocs: Optional[IOCCollectionResponse]
    threat_metadata: Optional[ThreatMetadataResponse]
    mitre_techniques: List[str] = []
    llm_raw_response: Optional[str]
    processing_status: Optional[str]  # SUCCESS / FAILED
    processing_timestamp: Optional[datetime]
    confidence_score: int = 0
    verification_status: str = "unknown"
    hallucination_count: int = 0
    evidence: Optional[Dict[str, str]]   # evidence_json parsed
    target_organization: List[str] = []
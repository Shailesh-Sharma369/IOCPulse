from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import hashlib


@dataclass
class RawArticle:
    """
    Represents one article as it will be persisted to staging_raw.

    Fields
    ------
    source_domain       : Org/name that owns the raw_html we store
                          (may be the original research org, not the publisher).
    source_url          : URL whose HTML is stored in raw_html.
    title               : Article title (from publisher or original source).
    author              : Author(s).
    published_datetime_utc : Publication date (UTC-aware).
    raw_html            : Extracted body HTML of the page at source_url.
    metadata_hash       : SHA-256 of "publisher_url|title" — dedup key.
    original_source_url : URL of the publisher article that led us here
                          (populated when we resolved an original source;
                          None when the publisher IS the primary source).
    source_status       : 'ORIGINAL' — raw_html is from the primary source.
                          'MIRROR'   — raw_html is from a publisher/aggregator.
    publisher_domain    : Name of the configured source (BleepingComputer etc.)
                          stored for reference when source_status='ORIGINAL'.
    publisher_url       : URL of the publisher article we first crawled,
                          stored for reference when source_status='ORIGINAL'.
    """
    source_domain: str
    source_url: str
    title: str
    author: str
    published_datetime_utc: Optional[datetime]
    raw_html: str
    metadata_hash: str
    original_source_url: Optional[str] = None
    source_status: str = 'MIRROR'
    # Publisher provenance — set when source_status='ORIGINAL'
    publisher_domain: Optional[str] = None
    publisher_url: Optional[str] = None
    ingestion_timestamp_utc: datetime = field(default_factory=datetime.utcnow)

    @classmethod
    def from_metadata(
        cls,
        source_domain: str,
        source_url: str,
        title: str,
        author: str,
        published: Optional[datetime],
        html: str,
        original_source_url: Optional[str] = None,
        source_status: str = 'MIRROR',
        publisher_domain: Optional[str] = None,
        publisher_url: Optional[str] = None,
    ) -> "RawArticle":
        # Hash is always keyed on the publisher URL + title so that the same
        # story crawled from different publishers gets distinct rows, but the
        # same publisher article is never duplicated even if we re-run ingestion.
        fingerprint_url = publisher_url or source_url
        raw_fingerprint = f"{fingerprint_url}|{title}".encode("utf-8")
        hash_ = hashlib.sha256(raw_fingerprint).hexdigest()
        return cls(
            source_domain=source_domain,
            source_url=source_url,
            title=title or "Untitled",
            author=author or "Unknown",
            published_datetime_utc=published,
            raw_html=html,
            metadata_hash=hash_,
            original_source_url=original_source_url,
            source_status=source_status,
            publisher_domain=publisher_domain,
            publisher_url=publisher_url,
        )

    def to_db_dict(self) -> dict:
        return {
            "metadata_hash": self.metadata_hash,
            "source_domain": self.source_domain,
            "source_url": self.source_url,
            "title": self.title,
            "author": self.author,
            "published_utc": self.published_datetime_utc.isoformat() if self.published_datetime_utc else None,
            "raw_html": self.raw_html,
            # original_source_url stores the publisher article URL when we
            # successfully resolved the original source (so Module 2 knows
            # where the story was first reported).  When source_status='MIRROR'
            # it stores the canonical URL detected during parsing (legacy).
            "original_source_url": self.original_source_url,
            "source_status": self.source_status,
        }
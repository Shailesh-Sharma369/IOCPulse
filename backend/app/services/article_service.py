import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from app.services.database_service import DatabaseService
from app.schemas.article import (
    RawArticleResponse, ProcessedArticleResponse,
    IOCCollectionResponse, ThreatMetadataResponse
)
from app.utils.exceptions import NotFoundError

logger = logging.getLogger(__name__)


class ArticleService:
    def __init__(self, db_service: DatabaseService):
        self.db_service = db_service

    # ---------- Helper to parse a processed article row ----------
    def _parse_processed_row(self, row: Dict[str, Any]) -> ProcessedArticleResponse:
        iocs = None
        if row.get("iocs_json"):
            try:
                iocs_data = json.loads(row["iocs_json"])
                iocs = IOCCollectionResponse(**iocs_data)
            except Exception as e:
                logger.warning(f"Failed to parse iocs_json: {e}")

        threat_meta = None
        if row.get("threat_metadata_json"):
            try:
                meta_data = json.loads(row["threat_metadata_json"])
                threat_meta = ThreatMetadataResponse(**meta_data)
            except Exception as e:
                logger.warning(f"Failed to parse threat_metadata_json: {e}")

        mitre = []
        if row.get("mitre_techniques_json"):
            try:
                mitre = json.loads(row["mitre_techniques_json"])
            except Exception as e:
                logger.warning(f"Failed to parse mitre_techniques_json: {e}")

        evidence = None
        if row.get("evidence_json"):
            try:
                evidence = json.loads(row["evidence_json"])
            except Exception as e:
                logger.warning(f"Failed to parse evidence_json: {e}")

        target_org = []
        if row.get("target_organization"):
            try:
                target_org = json.loads(row["target_organization"])
            except Exception as e:
                logger.warning(f"Failed to parse target_organization: {e}")

        # NEW: CVE enrichment (Phase 3)
        cve_details = None
        if row.get("cve_details_json"):
            try:
                parsed_cve = json.loads(row["cve_details_json"])
                if parsed_cve:   # skip empty {} stored by legacy rows
                    cve_details = parsed_cve
            except Exception as e:
                logger.warning(f"Failed to parse cve_details_json: {e}")

        # severity / tlp_tag with safe fallbacks for pre-migration rows
        severity = (row.get("severity") or "Unknown").strip() or "Unknown"
        tlp_tag  = (row.get("tlp_tag")  or "TLP:CLEAR").strip() or "TLP:CLEAR"

        return ProcessedArticleResponse(
            id=row["id"],
            metadata_hash=row["metadata_hash"],
            source_domain=row["source_domain"],
            source_url=row["source_url"],
            title=row["title"],
            author=row["author"],
            published_utc=row["published_utc"],
            original_source_url=row["original_source_url"],
            source_status=row["source_status"],
            retrieved_utc=row["retrieved_utc"],
            status=row["status"],
            processing_error=row["processing_error"],
            summary=row["summary"],
            severity=severity,
            tlp_tag=tlp_tag,
            cve_details=cve_details,     # NEW
            iocs=iocs,
            threat_metadata=threat_meta,
            mitre_techniques=mitre,
            llm_raw_response=row["llm_raw_response"],
            processing_status=row["processing_status"],
            processing_timestamp=row["processing_timestamp"],
            confidence_score=row["confidence_score"] or 0,
            verification_status=row["verification_status"] or "unknown",
            hallucination_count=row["hallucination_count"] or 0,
            evidence=evidence,
            target_organization=target_org,
        )

    # ---------- Raw Articles ----------
    async def list_raw_articles(
        self,
        page: int,
        page_size: int,
        source_domain: Optional[str] = None,
        status: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        sort_by: str = "published_utc",
        sort_dir: str = "DESC",
    ) -> Dict[str, Any]:
        offset = (page - 1) * page_size
        filters: Dict[str, Any] = {}
        if source_domain:
            filters["source_domain"] = source_domain
        if status:
            filters["status"] = status
        if date_from:
            filters["date_from"] = date_from
        if date_to:
            filters["date_to"] = date_to

        rows, total = await self.db_service.get_raw_articles(
            filters, offset, page_size, sort_by, sort_dir
        )
        items = [RawArticleResponse(**row) for row in rows]
        total_pages = (total + page_size - 1) // page_size
        return {
            "items": items,
            "pagination": {
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
            },
        }

    async def get_raw_article(self, article_id: int) -> RawArticleResponse:
        row = await self.db_service.get_raw_article_by_id(article_id)
        if not row:
            raise NotFoundError(f"Raw article with id {article_id} not found")
        return RawArticleResponse(**row)

    # ---------- Processed Articles ----------
    async def list_processed_articles(
        self,
        page: int,
        page_size: int,
        source_domain: Optional[str] = None,
        confidence_min: Optional[int] = None,
        verification_status: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        sort_by: str = "p.processing_timestamp",
        sort_dir: str = "DESC",
    ) -> Dict[str, Any]:
        offset = (page - 1) * page_size
        filters: Dict[str, Any] = {}
        if source_domain:
            filters["source_domain"] = source_domain
        if confidence_min is not None:
            filters["confidence_min"] = confidence_min
        if verification_status:
            filters["verification_status"] = verification_status
        if date_from:
            filters["date_from"] = date_from
        if date_to:
            filters["date_to"] = date_to

        rows, total = await self.db_service.get_processed_articles(
            filters, offset, page_size, sort_by, sort_dir
        )
        items = [self._parse_processed_row(row) for row in rows]
        total_pages = (total + page_size - 1) // page_size
        return {
            "items": items,
            "pagination": {
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
            },
        }

    async def get_processed_article(self, article_id: int) -> ProcessedArticleResponse:
        row = await self.db_service.get_processed_article_by_id(article_id)
        if not row:
            raise NotFoundError(f"Processed article with id {article_id} not found")
        return self._parse_processed_row(row)
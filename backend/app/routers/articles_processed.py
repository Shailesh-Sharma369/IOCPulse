from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.encoders import jsonable_encoder
from typing import Optional
from datetime import datetime
from src.shared.database import DatabaseClient
from app.dependencies import get_db
from app.services.database_service import DatabaseService
from app.services.article_service import ArticleService
from app.utils.response import success_response, error_response
from app.utils.exceptions import NotFoundError

router = APIRouter(prefix="/api/v1/articles/processed", tags=["processed articles"])

# Whitelist of allowed sort columns for processed articles (must include table alias)
ALLOWED_SORT_COLUMNS = {
    "p.processing_timestamp", "s.published_utc", "s.id", "s.title",
    "p.confidence_score", "p.verification_status",
    "p.severity", "p.tlp_tag",
}

@router.get("")
async def list_processed_articles(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    source_domain: Optional[str] = None,
    confidence_min: Optional[int] = Query(None, ge=0, le=100),
    verification_status: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    sort_by: str = Query("p.processing_timestamp", description="Column to sort by (e.g., p.processing_timestamp, s.published_utc)"),
    sort_dir: str = Query("DESC", pattern="^(ASC|DESC)$", description="Sort direction"),
    db: DatabaseClient = Depends(get_db)
):
    # Validate sort_by against whitelist
    if sort_by not in ALLOWED_SORT_COLUMNS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid sort_by column. Allowed: {', '.join(ALLOWED_SORT_COLUMNS)}"
        )

    db_service = DatabaseService(db)
    article_service = ArticleService(db_service)
    result = await article_service.list_processed_articles(
        page, page_size, source_domain, confidence_min,
        verification_status, date_from, date_to,
        sort_by, sort_dir
    )
    items_serializable = jsonable_encoder(result["items"])
    return success_response(
        data=items_serializable,
        pagination=result["pagination"]
    )

@router.get("/{article_id}")
async def get_processed_article(
    article_id: int,
    db: DatabaseClient = Depends(get_db)
):
    db_service = DatabaseService(db)
    article_service = ArticleService(db_service)
    try:
        article = await article_service.get_processed_article(article_id)
        return success_response(data=jsonable_encoder(article))
    except NotFoundError as e:
        return error_response(str(e), status_code=404)
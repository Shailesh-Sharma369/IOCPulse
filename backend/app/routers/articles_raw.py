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

router = APIRouter(prefix="/api/v1/articles/raw", tags=["raw articles"])

# Whitelist of allowed sort columns for raw articles
ALLOWED_SORT_COLUMNS = {"published_utc", "id", "title", "source_domain", "retrieved_utc", "status"}

@router.get("")
async def list_raw_articles(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    source_domain: Optional[str] = None,
    status: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    sort_by: str = Query("published_utc", description="Column to sort by (e.g., published_utc, id, title)"),
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
    result = await article_service.list_raw_articles(
        page, page_size, source_domain, status, date_from, date_to,
        sort_by, sort_dir
    )
    items_serializable = jsonable_encoder(result["items"])
    return success_response(
        data=items_serializable,
        pagination=result["pagination"]
    )

@router.get("/{article_id}")
async def get_raw_article(
    article_id: int,
    db: DatabaseClient = Depends(get_db)
):
    db_service = DatabaseService(db)
    article_service = ArticleService(db_service)
    try:
        article = await article_service.get_raw_article(article_id)
        return success_response(data=jsonable_encoder(article))
    except NotFoundError as e:
        return error_response(str(e), status_code=404)
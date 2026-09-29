from pydantic import BaseModel, Field
from typing import Optional, TypeVar, Generic

T = TypeVar("T")

class PaginationParams(BaseModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)

class PaginationResponse(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
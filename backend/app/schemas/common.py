"""Common response schemas."""
from typing import Any, Optional, Generic, TypeVar
from pydantic import BaseModel

T = TypeVar('T')


class Response(BaseModel, Generic[T]):
    """Standard API response."""
    code: int = 0
    message: str = "success"
    data: Optional[T] = None


class ErrorResponse(BaseModel):
    """Error response."""
    code: int
    message: str
    detail: Optional[str] = None


class PaginationParams(BaseModel):
    """Pagination parameters."""
    page: int = 1
    page_size: int = 10
    sort_by: str = "created_at"
    sort_order: str = "desc"

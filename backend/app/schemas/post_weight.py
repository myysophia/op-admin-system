"""Post weight schemas."""
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class PostWeightCreateRequest(BaseModel):
    """创建或更新帖子权重的请求体."""

    post_urls: str = Field(..., description="多个postURL，使用逗号分隔")
    weight: float = Field(..., description="权重值", ge=0)
    operator: Optional[str] = Field(None, description="操作人标识，默认使用当前登录用户")


class PostWeightCancelRequest(BaseModel):
    """批量取消帖子权重的请求体."""

    post_ids: List[str] = Field(..., min_length=1, description="需要取消权重的post_id列表")

    @model_validator(mode="after")
    def ensure_unique(self):
        unique = list(dict.fromkeys(self.post_ids))
        object.__setattr__(self, "post_ids", unique)
        return self


class PostWeightResponse(BaseModel):
    """帖子权重记录响应."""

    id: int
    post_url: str
    post_id: str
    weight: float
    operator: str
    operator_id: Optional[str] = Field(
        default=None, description="操作人ID，兼容旧字段operator"
    )
    operator_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    @field_validator("weight", mode="before")
    @classmethod
    def convert_decimal(cls, value):
        if isinstance(value, Decimal):
            return float(value)
        return value

    @model_validator(mode="after")
    def fill_operator_name(self):
        if self.operator_name is None:
            object.__setattr__(self, "operator_name", self.operator)
        if self.operator_id is None:
            object.__setattr__(self, "operator_id", self.operator)
        return self

    class Config:
        from_attributes = True


class PostWeightListResponse(BaseModel):
    """帖子权重记录列表响应."""

    items: List[PostWeightResponse]
    total: int
    page: int
    page_size: int

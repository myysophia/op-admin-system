"""Meme审核相关schema（保留旧字段名以兼容前端，数据源已改为DB）。"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# Kafka Meme Creation Message Schema
class MemeCreationMessage(BaseModel):
    """Schema for Meme creation message from Kafka."""
    user_id: str
    collection_id: str
    name: str  # Meme name
    symbol: str  # Meme symbol
    avatar: str  # Meme image URL
    about: str  # Description
    amount_to_buy: str
    gas: int
    chain_id: int
    social_links: Dict[str, Any] = Field(default_factory=dict)
    order_id: str  # Unique identifier for this meme creation request
    is_with_usdt: bool
    user_region: str
    holdview_amount: str

    # Kafka metadata (added by service)
    _kafka_offset: Optional[int] = None
    _kafka_partition: Optional[int] = None
    _kafka_timestamp: Optional[int] = None

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "BhnjgBmPBDZ",
                "collection_id": "BhwIj-XgpmH",
                "name": "匿名",
                "symbol": "HUO",
                "avatar": "https://images.dev.memefans.ai/6qpsuzob1760944958825",
                "about": "这是一个123asd",
                "amount_to_buy": "1",
                "gas": 7800000,
                "chain_id": 5918,
                "social_links": {},
                "order_id": "635f16e7-f35c-4d48-8f0e-6cdbfbbc02a5",
                "is_with_usdt": True,
                "user_region": "zh",
                "holdview_amount": "0"
            }
        }


class MemeReviewListItem(BaseModel):
    """待审核Meme列表项，kafka_timestamp现表示创建时间（来自DB）。"""
    order_id: str
    user_id: str
    collection_id: str
    name: str
    symbol: str
    avatar: str
    about: str
    chain_id: int
    social_links: Dict[str, Any]
    user_region: str
    holdview_amount: Optional[int] = None

    # Kafka metadata
    kafka_timestamp: Optional[datetime] = None

    # Author info (from join if available)
    creator_username: Optional[str] = None
    creator_name: Optional[str] = None

    class Config:
        from_attributes = True


class MemeReviewListResponse(BaseModel):
    """Response for meme review list."""
    items: List[MemeReviewListItem]
    total: int
    page: int
    page_size: int


class MemeReviewRequest(BaseModel):
    """Request to review a meme."""
    action: str = Field(..., pattern="^(approve|reject)$")
    comment: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "action": "approve",
                "comment": "Token verified, looks good"
            }
        }


class MemeSearchParams(BaseModel):
    """Search parameters for Meme review from DB."""
    user_id: Optional[str] = None
    symbol: Optional[str] = None
    name: Optional[str] = None

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=100)


class MemeMockLoadRequest(BaseModel):
    """Request body for loading mock meme messages (testing only)."""
    memes: List[MemeCreationMessage]

    class Config:
        json_schema_extra = {
            "example": {
                "memes": [
                    {
                        "user_id": "BhGJyRRIz0F",
                        "collection_id": "mock-collection-1",
                        "name": "测试代币A",
                        "symbol": "TESTA",
                        "avatar": "https://cdn.example.com/testa.png",
                        "about": "用于本地审核流程测试",
                        "amount_to_buy": "1",
                        "gas": 7800000,
                        "chain_id": 5918,
                        "social_links": {"twitter": "https://twitter.com/testa"},
                        "order_id": "mock-order-001",
                        "is_with_usdt": True,
                        "user_region": "zh",
                        "holdview_amount": "0"
                    }
                ]
            }
        }


# Keep old Pair-related schemas for direct DB queries if needed
class PairResponse(BaseModel):
    """Response for Pair (existing memes in DB)."""
    id: int
    address: Optional[str] = None
    chain: int
    base_name: str
    base_symbol: str
    base_description: str
    base_image_url: str
    creator_id: Optional[str] = None
    status: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PairListResponse(BaseModel):
    """Response for pair list (existing approved memes)."""
    items: List[PairResponse]
    total: int
    page: int
    page_size: int

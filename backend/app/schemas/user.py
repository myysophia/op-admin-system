"""User schemas - matching actual database structure."""
from datetime import datetime, date
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator


# User schemas
class UserBase(BaseModel):
    email: Optional[str] = None
    phone_number: Optional[str] = None
    status: str
    region: Optional[str] = None
    is_active: bool
    is_verified: bool

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value):
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value


class UserResponse(UserBase):
    id: str
    avatar_url: Optional[str] = None
    last_login_at: Optional[datetime] = None
    last_login_method: Optional[str] = None
    created_at: Optional[datetime] = None
    is_superuser: bool

    class Config:
        from_attributes = True


# Author schemas
class AuthorBase(BaseModel):
    username: str
    name: str
    avatar: Optional[str] = None
    dedication: Optional[str] = None
    description: Optional[str] = None


class AuthorResponse(AuthorBase):
    id: str
    user_id: str
    email: Optional[str] = None
    phone_number: Optional[str] = None
    likes_count: int
    posts_count: int
    region: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# Wallet schemas
class WalletResponse(BaseModel):
    id: str
    pubkey: str
    type: str  # sol or bsc
    status: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# Combined user detail response
class UserDetailResponse(BaseModel):
    """User detail data."""
    user: UserResponse
    author: Optional[AuthorResponse] = None
    wallets: List[WalletResponse] = Field(default_factory=list)
    im_id: Optional[str] = None
    role: Optional[str] = None
    agora_id: Optional[int] = None
    app_version: Optional[str] = None
    yidun_task_id: Optional[str] = None


# Ban schemas
class BanRequest(BaseModel):
    reason: str = Field(..., min_length=1, description="Ban reason")
    duration: Optional[int] = Field(None, gt=0, description="Ban duration in seconds, None for permanent")
    notify: bool = Field(default=False, description="Send notification")
    notify_message: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "reason": "test",
                "duration": 180,
                "notify": True,
                "notify_message": "Your account has been temporarily banned"
            }
        }


class UnbanRequest(BaseModel):
    reason: Optional[str] = Field(None, description="Unban reason (optional)")


class BanResponse(BaseModel):
    id: str
    user_id: str
    reason: Optional[str] = None
    ends_at: Optional[datetime] = None  # None means permanent
    imposed_by: str
    revoked_at: Optional[datetime] = None
    revoked_by: Optional[str] = None
    revoke_reason: Optional[str] = None
    created_at: datetime
    is_active: bool = Field(default=True)  # Computed field

    class Config:
        from_attributes = True


# Search/Filter schemas
class UserSearchParams(BaseModel):
    # Search fields
    user_id: Optional[str] = None
    username: Optional[str] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None
    wallet_address: Optional[str] = None  # pubkey

    # Filter fields
    status: Optional[str] = None
    is_active: Optional[bool] = None
    region: Optional[str] = None

    # Pagination
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=100)
    sort_by: str = Field(default="created_at")
    sort_order: str = Field(default="desc", pattern="^(asc|desc)$")

    class Config:
        extra = "ignore"


class UserListResponse(BaseModel):
    items: List["UserListItemResponse"]
    total: int
    page: int
    page_size: int


class UserUpdate(BaseModel):
    status: Optional[str] = None
    is_active: Optional[bool] = None
    is_verified: Optional[bool] = None
    region: Optional[str] = None
    preferred_languages: Optional[List[str]] = None

    class Config:
        extra = "forbid"


class BanUserRequest(BanRequest):
    """Backward-compatible alias for ban request schema."""


class UnbanUserRequest(UnbanRequest):
    """Backward-compatible alias for unban request schema."""


class UserListItemResponse(BaseModel):
    """Lightweight user list item."""

    user_id: str
    username: Optional[str] = None
    display_name: Optional[str] = None
    created_at: Optional[datetime] = None
    bsc_wallet: Optional[str] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None
    status: str


UserListResponse.model_rebuild()


class BanHistoryItem(BaseModel):
    id: int
    action: str
    reason: Optional[str] = None
    duration_seconds: Optional[int] = None
    operator_id: str
    created_at: datetime

    class Config:
        from_attributes = True


class BanHistoryListResponse(BaseModel):
    items: List[BanHistoryItem]
    total: int

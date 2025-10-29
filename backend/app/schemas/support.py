"""Support schemas - simplified without WebSocket (using OpenIM)."""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# Conversation schemas
class ConversationResponse(BaseModel):
    """Conversation response model."""
    id: str
    user_id: str
    operator_id: Optional[str] = None
    status: str  # pending, in_progress, later, ended
    openim_conversation_id: Optional[str] = None
    has_unread_messages: bool = False
    unread_count: int = 0
    last_message_at: Optional[datetime] = None
    last_message_from: Optional[str] = None  # user or operator
    last_message_preview: Optional[str] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime
    user_info: Optional[Dict[str, Any]] = None
    operator_info: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class ConversationListResponse(BaseModel):
    """Paginated conversation list response."""
    items: List[ConversationResponse]
    total: int
    page: int
    page_size: int


class ConversationSearchParams(BaseModel):
    """Search parameters for conversations."""
    status: Optional[str] = Field(None, description="pending, in_progress, later, ended")
    user_id: Optional[str] = None
    has_unread: Optional[bool] = None
    sort_by: str = Field(default="priority", description="priority, last_message_at, created_at, unread_count")
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class ConversationDetailResponse(BaseModel):
    """Conversation detail with messages from OpenIM."""
    id: str
    user_id: str
    operator_id: Optional[str] = None
    status: str
    openim_conversation_id: Optional[str] = None
    last_message_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime
    user_info: Optional[Dict[str, Any]] = None
    messages: List[Dict[str, Any]] = []  # Messages from OpenIM


class AssignConversationRequest(BaseModel):
    """Request to assign conversation to operator."""
    operator_id: str = Field(..., description="Operator user ID")


class UpdateConversationStatusRequest(BaseModel):
    """Request to update conversation status."""
    status: str = Field(..., pattern="^(later|ended|in_progress)$")


# Message schemas
class SendMessageRequest(BaseModel):
    """Request to send message via OpenIM."""
    content: str = Field(..., min_length=1, description="Message content")
    content_type: int = Field(default=101, description="OpenIM content type (101=text)")


class BatchSendMessageRequest(BaseModel):
    """Request to send message to multiple conversations."""
    conversation_ids: List[str] = Field(..., min_items=1, description="List of conversation IDs")
    content: str = Field(..., min_length=1, description="Message content")
    content_type: int = Field(default=101, description="OpenIM content type")


class BatchSendMessageResponse(BaseModel):
    """Response for batch send message."""
    total: int
    success: int
    failed: int
    details: List[Dict[str, Any]]


# Quick reply schemas
class QuickReplyBase(BaseModel):
    """Base quick reply model."""
    title: str = Field(..., min_length=1, max_length=100)
    content: str = Field(..., min_length=1)
    is_shared: bool = Field(default=False, description="Whether shared with all operators")


class QuickReplyCreate(QuickReplyBase):
    """Create quick reply request."""
    pass


class QuickReplyUpdate(BaseModel):
    """Update quick reply request."""
    title: Optional[str] = Field(None, min_length=1, max_length=100)
    content: Optional[str] = Field(None, min_length=1)
    is_shared: Optional[bool] = None


class QuickReplyResponse(QuickReplyBase):
    """Quick reply response."""
    id: int
    operator_id: str
    usage_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class QuickReplyListResponse(BaseModel):
    """Quick reply list response."""
    items: List[QuickReplyResponse]
    total: int

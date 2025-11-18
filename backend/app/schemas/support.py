"""Support schemas for会话状态管理."""
from datetime import datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, Field
from pydantic.config import ConfigDict


class SupportConversationMessage(BaseModel):
    """单条会话消息摘要."""
    sender_id: Optional[str] = None
    sender_type: Literal["user", "operator", "system"] = "user"
    content: str = Field(..., description="消息内容")
    sent_at: Optional[datetime] = Field(None, description="发送时间")


class SupportConversationCreateRequest(BaseModel):
    """创建或更新会话的请求."""
    openim_conversation_id: str = Field(..., description="OpenIM会话ID")
    user_id: str = Field(..., description="用户ID")
    last_message: Optional[str] = None
    last_message_at: Optional[datetime] = None
    messages: List[SupportConversationMessage] = Field(default_factory=list)
    device_type: Optional[str] = None
    device_id: Optional[str] = None
    app_version: Optional[str] = None
    task_id: Optional[str] = None


class SupportConversationCreateResponse(BaseModel):
    """创建/更新完成后的响应."""
    conversation_id: str
    status: str


class SupportConversationListItem(BaseModel):
    """会话列表单项."""
    conversation_id: str
    openim_conversation_id: str
    user_id: str
    username: Optional[str] = None
    display_name: Optional[str] = None
    wallet_address: Optional[str] = None
    status: str
    last_message: Optional[str] = None
    last_message_at: Optional[datetime] = None
    app_version: Optional[str] = None


class SupportConversationListResponse(BaseModel):
    """会话列表响应."""
    items: List[SupportConversationListItem]
    total: int
    page: int
    page_size: int


class SupportConversationUserProfile(BaseModel):
    """会话右侧面板所需用户信息."""
    user_id: str
    username: Optional[str] = None
    display_name: Optional[str] = None
    wallet_address: Optional[str] = None
    agora_uid: Optional[int] = None
    im_id: Optional[str] = None
    task_id: Optional[str] = None
    device_type: Optional[str] = None
    device_id: Optional[str] = None
    app_version: Optional[str] = None
    registered_email: Optional[str] = None
    tel: Optional[str] = None


class SupportConversationDetailResponse(BaseModel):
    """会话详情响应."""
    conversation_id: str
    openim_conversation_id: str
    status: str
    last_message: Optional[str] = None
    last_message_at: Optional[datetime] = None
    messages: List[SupportConversationMessage] = Field(default_factory=list)
    user_profile: SupportConversationUserProfile


class SupportConversationStatusUpdateRequest(BaseModel):
    """更新会话状态请求."""
    status: Literal["pending", "processed", "later"]


class SupportConversationQuery(BaseModel):
    """会话查询参数."""
    status: Optional[Literal["pending", "processed", "later"]] = None
    uid: Optional[str] = None
    username: Optional[str] = None
    display_name: Optional[str] = None
    wallet_address: Optional[str] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=100)


class SupporterListResponse(BaseModel):
    """客服超级管理员列表响应。"""
    supporters: List[str] = Field(default_factory=list, description="超级管理员ID列表")


class SupportImLookupRequest(BaseModel):
    """批量IM ID查询请求."""
    im_ids: List[str] = Field(..., min_items=1, description="OpenIM im_id 列表")


class SupportImLookupItem(BaseModel):
    """单个IM映射结果."""
    im_id: str
    found: bool
    user_profile: Optional[SupportConversationUserProfile] = None


class SupportImLookupResponse(BaseModel):
    """批量IM映射响应."""
    items: List[SupportImLookupItem]


# ------------------------------- 快捷消息 ------------------------------- #


class SupportQuickMessageBase(BaseModel):
    """快捷消息基础字段."""

    title: str = Field(..., max_length=100, description="消息标题")
    content: str = Field(..., description="消息正文，支持文本+表情")
    sort_order: int = Field(default=100, ge=0, le=10000, description="排序值，越小越靠前")
    is_active: bool = Field(default=True, description="是否启用")
    image_key: Optional[str] = Field(default=None, description="R2对象Key")
    image_url: Optional[str] = Field(default=None, description="图片访问URL")


class SupportQuickMessageCreateRequest(SupportQuickMessageBase):
    """创建快捷消息请求."""

    model_config = ConfigDict(extra="forbid")


class SupportQuickMessageUpdateRequest(BaseModel):
    """更新快捷消息请求."""

    title: Optional[str] = Field(default=None, max_length=100)
    content: Optional[str] = None
    sort_order: Optional[int] = Field(default=None, ge=0, le=10000)
    is_active: Optional[bool] = None
    image_key: Optional[str] = None
    image_url: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class SupportQuickMessageItem(SupportQuickMessageBase):
    """快捷消息响应项."""

    id: str
    created_by: str
    created_by_name: Optional[str] = None
    updated_by: Optional[str] = None
    updated_by_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SupportQuickMessageListResponse(BaseModel):
    """快捷消息列表响应."""

    items: List[SupportQuickMessageItem]


class SupportQuickMessageUploadResponse(BaseModel):
    """图片上传结果."""

    key: str
    url: str
    content_type: str
    size: int

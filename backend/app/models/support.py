"""Support conversation model for状态管理."""
from datetime import datetime
import uuid
from typing import Optional
from sqlalchemy import Boolean, Integer, String, DateTime, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class SupportConversation(Base):
    """Customer support conversation."""

    __tablename__ = "support_conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    operator_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    openim_conversation_id: Mapped[Optional[str]] = mapped_column(String(128), unique=True, index=True)

    last_message: Mapped[Optional[str]] = mapped_column(Text)
    last_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime, index=True)
    messages: Mapped[Optional[list]] = mapped_column(JSON, default=list)

    task_id: Mapped[Optional[str]] = mapped_column(String(128))
    device_type: Mapped[Optional[str]] = mapped_column(String(64))
    device_id: Mapped[Optional[str]] = mapped_column(String(128))
    app_version: Mapped[Optional[str]] = mapped_column(String(32))

    operator_name: Mapped[Optional[str]] = mapped_column(String(128))
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SupportQuickMessage(Base):
    """Support快捷回复模板."""

    __tablename__ = "support_quick_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    image_key: Mapped[Optional[str]] = mapped_column(String(255))
    image_url: Mapped[Optional[str]] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_name: Mapped[Optional[str]] = mapped_column(String(128))
    updated_by: Mapped[Optional[str]] = mapped_column(String(64))
    updated_by_name: Mapped[Optional[str]] = mapped_column(String(128))

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

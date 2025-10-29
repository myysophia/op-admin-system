"""Support and audit models - new tables for OP admin."""
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, DateTime, Boolean, Text, JSON, BigInteger, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class SupportConversation(Base):
    """Support conversation model - NEW TABLE."""
    __tablename__ = "support_conversations"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False, index=True)
    operator_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("users.id"), index=True)

    # Status: pending (待处理), in_progress (处理中), later (稍后回复), ended (已结束)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending", index=True)

    # OpenIM conversation ID for chat
    openim_conversation_id: Mapped[Optional[str]] = mapped_column(String, index=True)

    # Unread message indicator for operator
    has_unread_messages: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    unread_count: Mapped[int] = mapped_column(Integer, default=0)

    # Last message info
    last_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime, index=True)
    last_message_from: Mapped[Optional[str]] = mapped_column(String)  # user or operator
    last_message_preview: Mapped[Optional[str]] = mapped_column(String(200))

    # Resolution time (when status changed to 'ended')
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    operator = relationship("User", foreign_keys=[operator_id])


class QuickReply(Base):
    """Quick reply template model - NEW TABLE."""
    __tablename__ = "quick_replies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operator_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    is_shared: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    operator = relationship("User")


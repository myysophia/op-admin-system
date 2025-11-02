"""Ban history model."""
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class BanHistory(Base):
    """Ban and unban history record."""

    __tablename__ = "ban_his"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(10), nullable=False)  # ban / unban
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ban_method: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    operator_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    operator_id: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)

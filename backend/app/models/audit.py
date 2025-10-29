"""Audit log model."""
from datetime import datetime
from typing import Optional
from sqlalchemy import BigInteger, String, Text, DateTime, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class OperatorAuditLog(Base):
    """Operator audit log model."""

    __tablename__ = "operator_audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    operator_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id"), nullable=False, index=True
    )
    action_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    target_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    target_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    action_details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

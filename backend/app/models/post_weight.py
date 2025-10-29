"""Post weight model."""
from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, Numeric, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class PostWeight(Base):
    """Post weight configuration."""

    __tablename__ = "post_weights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    post_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    post_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    weight: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    operator: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)

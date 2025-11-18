"""Configuration related tables (startup modes & app versions)."""
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class StartupMode(Base):
    """Startup mode configuration per OS/build."""

    __tablename__ = "startup_modes"

    os: Mapped[str] = mapped_column(String, primary_key=True)
    build: Mapped[str] = mapped_column(String, primary_key=True)
    mode: Mapped[str] = mapped_column(String, nullable=False)


class AppVersion(Base):
    """Application version release metadata."""

    __tablename__ = "app_versions"

    version: Mapped[str] = mapped_column(String, primary_key=True)
    target_os: Mapped[str] = mapped_column(String, primary_key=True)
    build: Mapped[int] = mapped_column(Integer, primary_key=True)
    force_update: Mapped[bool] = mapped_column(Boolean, primary_key=True, default=False)

    release_date: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    release_notes: Mapped[Optional[str]] = mapped_column(Text)
    download_url: Mapped[Optional[str]] = mapped_column(Text)
    extra: Mapped[Optional[dict]] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

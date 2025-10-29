"""User related models - matching existing database schema."""
from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Boolean, DateTime, ARRAY, Date, Integer, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class User(Base):
    """User model - authentication table."""
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    email: Mapped[Optional[str]] = mapped_column(String(320), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(1024), nullable=False)
    phone_number: Mapped[Optional[str]] = mapped_column(String, unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_virtual: Mapped[Optional[bool]] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(String, nullable=False)
    region: Mapped[Optional[str]] = mapped_column(String)
    preferred_languages: Mapped[List[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    google_id: Mapped[Optional[str]] = mapped_column(String, unique=True, index=True)
    apple_id: Mapped[Optional[str]] = mapped_column(String, unique=True, index=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String)
    google_linked_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    apple_linked_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    email_verified_via: Mapped[Optional[str]] = mapped_column(String)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_login_method: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Relationships
    author = relationship("Author", back_populates="user", uselist=False)
    wallets = relationship("UserWallet", back_populates="user")
    bans = relationship("Ban", foreign_keys="Ban.user_id", back_populates="user")


class Author(Base):
    """Author model - creator profile table."""
    __tablename__ = "authors"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    username_raw: Mapped[str] = mapped_column(String, unique=True, nullable=False)  # citext in DB
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar: Mapped[Optional[str]] = mapped_column(String(255))
    original_avatar: Mapped[Optional[str]] = mapped_column(String(255))
    dedication: Mapped[Optional[str]] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(String(300))
    location: Mapped[Optional[str]] = mapped_column(String(255))
    country: Mapped[Optional[str]] = mapped_column(String(255))
    language: Mapped[Optional[str]] = mapped_column(String(255))
    education: Mapped[Optional[str]] = mapped_column(String(255))
    email: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    phone_number: Mapped[Optional[str]] = mapped_column(String(255), index=True)
    birthday: Mapped[Optional[datetime]] = mapped_column(Date)
    gender: Mapped[Optional[str]] = mapped_column(String)
    region: Mapped[str] = mapped_column(String, nullable=False)
    likes_count: Mapped[int] = mapped_column(Integer, nullable=False)
    citations_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    posts_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pins: Mapped[List[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    invitation_id: Mapped[Optional[str]] = mapped_column(String)
    invitation_id_owned: Mapped[Optional[str]] = mapped_column(String(50))
    group_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    group_grade: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    direct_invited_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    vip_code: Mapped[Optional[str]] = mapped_column(String(20))
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Relationships
    user = relationship("User", back_populates="author")
    posts = relationship("Post", back_populates="author")


class UserWallet(Base):
    """User wallet model."""
    __tablename__ = "user_wallet"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False, index=True)
    pubkey: Mapped[str] = mapped_column(Text, nullable=False, default="", index=True)
    secret: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False, default="")  # sol or bsc
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Relationships
    user = relationship("User", back_populates="wallets")


class Ban(Base):
    """Ban record model."""
    __tablename__ = "bans"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False, index=True)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime)  # NULL means permanent
    imposed_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    revoked_by: Mapped[Optional[str]] = mapped_column(String, ForeignKey("users.id"))
    revoke_reason: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Relationships
    user = relationship("User", foreign_keys=[user_id], back_populates="bans")
    imposer = relationship("User", foreign_keys=[imposed_by])
    revoker = relationship("User", foreign_keys=[revoked_by])

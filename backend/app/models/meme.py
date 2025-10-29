"""Meme and Post models."""
from datetime import datetime
from sqlalchemy import BigInteger, String, Text, DateTime, DECIMAL, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Meme(Base):
    """Meme model."""

    __tablename__ = "memes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    meme_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    meme_name: Mapped[str] = mapped_column(String(255), nullable=False)
    meme_description: Mapped[str] = mapped_column(Text, nullable=True)
    cover_image_url: Mapped[str] = mapped_column(String(500), nullable=True)
    creator_uid: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    creator_username: Mapped[str] = mapped_column(String(50), nullable=True)
    chat_amount: Mapped[float] = mapped_column(DECIMAL(20, 2), default=0)
    cion_amount: Mapped[float] = mapped_column(DECIMAL(20, 2), default=0)
    url: Mapped[str] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    review_operator_id: Mapped[int] = mapped_column(BigInteger, nullable=True)
    review_time: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    review_comment: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    creator = relationship("User", back_populates="memes", foreign_keys=[creator_uid])
    review_records = relationship("MemeReviewRecord", back_populates="meme")
    posts = relationship("Post", back_populates="meme")


class MemeReviewRecord(Base):
    """Meme review record model."""

    __tablename__ = "meme_review_records"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    meme_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    operator_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(20), nullable=False)  # approve, reject
    comment: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    meme = relationship("Meme", back_populates="review_records")


class Post(Base):
    """Post model."""

    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    post_url: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    meme_id: Mapped[int] = mapped_column(BigInteger, nullable=True, index=True)
    creator_uid: Mapped[int] = mapped_column(BigInteger, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=True)
    weight: Mapped[int] = mapped_column(Integer, default=0, index=True)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    meme = relationship("Meme", back_populates="posts")
    weight_records = relationship("PostWeightRecord", back_populates="post")


class PostWeightRecord(Base):
    """Post weight adjustment record model."""

    __tablename__ = "post_weight_records"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    post_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    operator_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    old_weight: Mapped[int] = mapped_column(Integer, nullable=True)
    new_weight: Mapped[int] = mapped_column(Integer, nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    post = relationship("Post", back_populates="weight_records")

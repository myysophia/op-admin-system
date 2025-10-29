"""Post and Pair (Meme) models - matching existing database schema."""
from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Integer, DateTime, ARRAY, Text, Numeric, SmallInteger, DECIMAL, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey
from app.database import Base


class Post(Base):
    """Post model - base table for all content types."""
    __tablename__ = "posts"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    author_id: Mapped[str] = mapped_column(String, ForeignKey("authors.id"), nullable=False, index=True)
    type: Mapped[Optional[str]] = mapped_column(String)  # images, videos, collections
    status: Mapped[str] = mapped_column(String, nullable=False)  # posted, draft, deleted, etc
    region: Mapped[str] = mapped_column(String, nullable=False)
    language: Mapped[str] = mapped_column(String, nullable=False, default="global")
    source: Mapped[Optional[str]] = mapped_column(Text, default="user")

    # Counts and metrics
    likes_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    comments_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    collections_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    complaint_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    interaction_rating: Mapped[float] = mapped_column(Numeric, nullable=False, default=0)

    # Token binding
    binding_token: Mapped[Optional[str]] = mapped_column(String)  # Reference to pair.address

    # Content moderation
    yi_dun_check: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Premium content
    holdview_amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Versioning
    current_version_id: Mapped[Optional[str]] = mapped_column(String)

    # Tags
    tags_list: Mapped[List[str]] = mapped_column(ARRAY(String), nullable=False, default=list)

    # Timestamps
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, index=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    publish_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Relationships
    author = relationship("Author", back_populates="posts")
    image = relationship("Image", back_populates="post", uselist=False)
    video = relationship("Video", back_populates="post", uselist=False)
    collection = relationship("Collection", back_populates="post", uselist=False)


class Image(Base):
    """Image post model."""
    __tablename__ = "images"

    id: Mapped[str] = mapped_column(String, ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True)
    title: Mapped[Optional[str]] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(String)
    cover: Mapped[Optional[str]] = mapped_column(String(1024))
    width: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    height: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    images_data: Mapped[Optional[dict]] = mapped_column(JSON)  # JSONB in DB

    # Relationships
    post = relationship("Post", back_populates="image")


class Video(Base):
    """Video post model."""
    __tablename__ = "videos"

    id: Mapped[str] = mapped_column(String, ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True)
    url: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(String)
    cover: Mapped[Optional[str]] = mapped_column(String(1024))
    url_type: Mapped[Optional[str]] = mapped_column(String)
    processing_status: Mapped[Optional[str]] = mapped_column(String)
    uid: Mapped[Optional[str]] = mapped_column(Text, unique=True)  # Cloudflare UID
    metainfo: Mapped[Optional[dict]] = mapped_column(JSON)  # JSONB in DB
    width: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    height: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    free_seconds: Mapped[Optional[int]] = mapped_column(Integer, default=0)

    # Relationships
    post = relationship("Post", back_populates="video")


class Collection(Base):
    """Collection post model."""
    __tablename__ = "collections"

    id: Mapped[str] = mapped_column(String, ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True)
    title: Mapped[Optional[str]] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(String)
    cover: Mapped[Optional[str]] = mapped_column(String(1024))
    original_cover: Mapped[Optional[str]] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String, nullable=False, default="Mixed")
    contents: Mapped[List[str]] = mapped_column(ARRAY(String), nullable=False)  # Post IDs
    contents_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pins: Mapped[List[str]] = mapped_column(ARRAY(String), nullable=False, default=list)

    # Carnival related
    carnival_status: Mapped[str] = mapped_column(String, nullable=False, default="new")
    carnival_start_time: Mapped[Optional[datetime]] = mapped_column(DateTime)
    carnival_points_pool: Mapped[float] = mapped_column(Numeric, nullable=False, default=0)
    subscriber_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    contributor_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Relationships
    post = relationship("Post", back_populates="collection")


class Pair(Base):
    """Pair model - Meme token information."""
    __tablename__ = "pair"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Chain and DEX info
    chain: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    address: Mapped[Optional[str]] = mapped_column(Text, unique=True, index=True)
    dex: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Base token (the Meme token)
    base: Mapped[Optional[str]] = mapped_column(Text, index=True)
    base_decimals: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    base_name: Mapped[str] = mapped_column(Text, nullable=False, default="", index=True)
    base_symbol: Mapped[str] = mapped_column(Text, nullable=False, default="", index=True)
    base_image_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    base_description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    base_total_supply: Mapped[int] = mapped_column(Numeric(78, 0), nullable=False, default=0)
    base_created_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Quote token
    quote: Mapped[Optional[str]] = mapped_column(Text)
    quote_decimals: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)

    # Amounts
    base_amount: Mapped[int] = mapped_column(Numeric(78, 0), nullable=False, default=0)
    quote_amount: Mapped[int] = mapped_column(Numeric(78, 0), nullable=False, default=0)

    # Creator info
    creator: Mapped[str] = mapped_column(Text, nullable=False, default="")
    creator_id: Mapped[Optional[str]] = mapped_column(Text, index=True)  # user_id or author_id

    # Collection binding
    collection_id: Mapped[Optional[str]] = mapped_column(Text, index=True)

    # Market data
    price_usd: Mapped[float] = mapped_column(Numeric(38, 18), nullable=False, default=0)
    liq: Mapped[int] = mapped_column(Numeric(78, 0), nullable=False, default=0)  # Liquidity
    mc: Mapped[int] = mapped_column(Numeric(78, 0), nullable=False, default=0)  # Market cap
    bonding_curve: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)

    # Status (0 = not displayed/pending review, 1 = data ready/approved)
    status: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, index=True)

    # Transaction info
    creation_txid: Mapped[Optional[str]] = mapped_column(Text, index=True)

    # Social links
    social_links: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)  # JSONB in DB

    # Timestamps
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    open_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

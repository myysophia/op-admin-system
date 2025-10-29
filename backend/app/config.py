"""Application configuration."""
import os
from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings."""

    # Application
    APP_NAME: str = "OP Admin System"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    SECRET_KEY: str = Field(..., min_length=32)

    # Database
    DATABASE_URL: str = Field(..., description="PostgreSQL connection URL")
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_PASSWORD: str = ""

    # JWT
    JWT_SECRET_KEY: str = Field(..., min_length=32)
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # OpenIM
    OPENIM_API_URL: str
    OPENIM_WS_URL: str
    OPENIM_SECRET: str
    OPENIM_ADMIN_USER_ID: str = "admin"
    OPENIM_PLATFORM_ID: int = 1

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000"]

    # Pagination
    DEFAULT_PAGE_SIZE: int = 10
    MAX_PAGE_SIZE: int = 100

    # File Upload
    MAX_UPLOAD_SIZE: int = 10485760  # 10MB
    UPLOAD_DIR: str = "./uploads"

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "./logs/app.log"

    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str = "meme-kafka-01.aurora:9092"
    KAFKA_CONSUMER_GROUP: str = "op-admin-meme-review"
    KAFKA_MEME_CREATION_TOPIC: str = "memecoin.meme_creation"
    KAFKA_MEME_APPROVED_TOPIC: str = "memecoin.meme_approved"
    KAFKA_AUTO_OFFSET_RESET: str = "earliest"  # earliest or latest

    # External Notification API
    NOTIFICATION_API_URL: str = "http://toci-dev-01.aurora:8014"

    # Recommendation / Post Weighting
    POST_WEIGHT_API_URL: Optional[str] = None
    POST_WEIGHT_API_TOKEN: Optional[str] = None

    class Config:
        env_file = ".env"
        case_sensitive = True


# Create settings instance
settings = Settings()

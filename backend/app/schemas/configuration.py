"""Schemas for configuration (startup modes & app versions)."""
from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import AnyUrl, BaseModel, Field
from pydantic.config import ConfigDict


class StartupModeItem(BaseModel):
    os: str
    build: str
    mode: str

    model_config = ConfigDict(from_attributes=True)


class StartupModeListResponse(BaseModel):
    items: list[StartupModeItem]


class StartupModeUpdateItem(BaseModel):
    os: str = Field(..., description="Target OS, e.g. ios/android")
    build: str = Field(..., description="Build version string")
    mode: str = Field(default="normal", description="Startup mode, e.g. normal/strict")


class StartupModeUpdateRequest(BaseModel):
    items: list[StartupModeUpdateItem] = Field(..., min_items=1, description="Startup mode entries to add")


class PublishVersionRequest(BaseModel):
    """Publish app build to external mode API."""

    build: str = Field(..., description="Build version string, e.g. 1.2.13")
    os: str = Field(..., description="Target platform, e.g. ios or android")


class AppVersionInfo(BaseModel):
    target_os: str
    version: str
    build: int
    release_notes: Optional[str] = None
    download_url: Optional[AnyUrl] = None
    release_date: datetime
    force_update: bool
    extra: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


class PlatformVersionInfo(BaseModel):
    optional: Optional[AppVersionInfo] = None
    mandatory: Optional[AppVersionInfo] = None


class AppVersionConfigResponse(BaseModel):
    ios: PlatformVersionInfo = Field(default_factory=PlatformVersionInfo)
    android: PlatformVersionInfo = Field(default_factory=PlatformVersionInfo)


class AppVersionUpdatePayload(BaseModel):
    version: str = Field(..., description="Human readable version string, e.g. 1.2.6")
    build: int = Field(..., ge=1, description="Internal build number")
    download_url: Optional[AnyUrl] = Field(default=None, description="Optional download URL for the app binary")
    release_notes: Optional[str] = Field(default=None, description="Release notes shown to end users")
    release_date: Optional[datetime] = Field(default=None, description="Release time; defaults to current time if omitted")
    extra: Optional[Dict[str, Any]] = Field(default=None, description="Additional JSON configuration for this version")


class PlatformVersionUpdate(BaseModel):
    optional: Optional[AppVersionUpdatePayload] = None
    mandatory: Optional[AppVersionUpdatePayload] = None


class AppVersionConfigUpdateRequest(BaseModel):
    ios: Optional[PlatformVersionUpdate] = None
    android: Optional[PlatformVersionUpdate] = None


class ExternalAppVersionUpdateRequest(BaseModel):
    """Request body forwarded to external version upgrade API (fields aligned with external service)."""

    version: str = Field(..., description="Human readable version string, e.g. 1.2.6")
    build: int = Field(..., ge=0, description="Internal build number")
    target_os: str = Field(..., description="Target platform, e.g. ios or android")
    release_date: Optional[datetime] = Field(
        default=None,
        description="Release time in ISO8601; if omitted, external service decides",
    )
    release_notes: Optional[str] = Field(default=None, description="Release notes displayed to end users")
    download_url: Optional[AnyUrl] = Field(default=None, description="Download URL for the app binary")
    force_update: bool = Field(default=False, description="Whether this version requires a mandatory upgrade")

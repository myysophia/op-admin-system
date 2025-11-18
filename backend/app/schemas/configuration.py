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
    version: str = Field(..., description="客户端展示的版本号")
    build: int = Field(..., ge=1, description="内部build号")
    download_url: Optional[AnyUrl] = Field(default=None, description="安装包地址")
    release_notes: Optional[str] = Field(default=None, description="更新提示文案")
    release_date: Optional[datetime] = Field(default=None, description="发布时间，不填默认当前时间")
    extra: Optional[Dict[str, Any]] = Field(default=None, description="附加配置，JSON结构")


class PlatformVersionUpdate(BaseModel):
    optional: Optional[AppVersionUpdatePayload] = None
    mandatory: Optional[AppVersionUpdatePayload] = None


class AppVersionConfigUpdateRequest(BaseModel):
    ios: Optional[PlatformVersionUpdate] = None
    android: Optional[PlatformVersionUpdate] = None

"""Configuration service for startup modes & app versions."""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional
import logging

import httpx
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.configuration import AppVersion, StartupMode
from app.schemas.configuration import (
    AppVersionConfigResponse,
    AppVersionConfigUpdateRequest,
    AppVersionInfo,
    AppVersionUpdatePayload,
    ExternalAppVersionUpdateRequest,
    PlatformVersionInfo,
    PlatformVersionUpdate,
    PublishVersionRequest,
    StartupModeItem,
    StartupModeListResponse,
)
from app.services.audit_service import AuditService

logger = logging.getLogger(__name__)


class ConfigurationService:
    """Service layer for configuration management."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.audit_service = AuditService(db)

    # ------------------------------------------------------------------ #
    async def list_startup_modes(
        self,
        mode: Optional[str] = "normal",
        os_filter: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
    ) -> StartupModeListResponse:
        stmt = select(StartupMode)
        if mode:
            stmt = stmt.where(StartupMode.mode == mode)
        if os_filter:
            stmt = stmt.where(StartupMode.os == os_filter)

        stmt = stmt.order_by(StartupMode.os.asc(), StartupMode.build.desc())
        stmt = stmt.limit(limit).offset(offset)

        result = await self.db.execute(stmt)
        rows = result.scalars().all()
        items = [StartupModeItem.model_validate(row) for row in rows]
        return StartupModeListResponse(items=items)

    # ------------------------------------------------------------------ #
    async def get_app_version_config(
        self,
        page: int = 1,
        page_size: int = 10,
    ) -> AppVersionConfigResponse:
        row_number = func.row_number().over(
            partition_by=(AppVersion.target_os, AppVersion.force_update),
            order_by=[
                AppVersion.release_date.desc(),
                AppVersion.updated_at.desc().nullslast(),
                AppVersion.created_at.desc().nullslast(),
            ],
        )

        ranked_stmt = select(AppVersion, row_number.label("row_rank"))
        result = await self.db.execute(ranked_stmt)

        platforms: Dict[str, PlatformVersionInfo] = {
            "ios": PlatformVersionInfo(),
            "android": PlatformVersionInfo(),
        }

        for version_obj, rank in result.all():
            if rank != 1:
                continue
            info = AppVersionInfo.model_validate(version_obj)
            slot = "mandatory" if version_obj.force_update else "optional"
            platform_key = version_obj.target_os.lower()
            if platform_key not in platforms:
                platforms[platform_key] = PlatformVersionInfo()
            setattr(platforms[platform_key], slot, info)

        return AppVersionConfigResponse(
            ios=platforms.get("ios", PlatformVersionInfo()),
            android=platforms.get("android", PlatformVersionInfo()),
        )

    # ------------------------------------------------------------------ #
    async def update_app_versions(
        self,
        payload: AppVersionConfigUpdateRequest,
        operator_id: str,
        operator_name: str,
    ) -> AppVersionConfigResponse:
        entries = self._extract_entries(payload)
        if not entries:
            raise HTTPException(status_code=400, detail="未提供任何需要更新的版本信息")

        saved: List[AppVersion] = []
        for entry in entries:
            release_dt = entry.release_date or datetime.utcnow()
            # Normalize timezone-aware datetimes to naive UTC to match TIMESTAMP WITHOUT TIME ZONE
            if getattr(release_dt, "tzinfo", None) is not None:
                release_dt = release_dt.astimezone(tz=None).replace(tzinfo=None)

            version = AppVersion(
                version=entry.version,
                build=entry.build,
                target_os=entry.target_os,
                force_update=entry.force_update,
                release_notes=entry.release_notes,
                download_url=str(entry.download_url) if entry.download_url else None,
                release_date=release_dt,
                extra=entry.extra,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            self.db.add(version)
            saved.append(version)

        await self.db.commit()

        # Refresh to populate defaults
        for version in saved:
            await self.db.refresh(version)

        await self.audit_service.log_action(
            operator_id=operator_id,
            action_type="configuration_app_versions_update",
            target_type="app_version",
            target_id="app_versions",
            action_details={
                "operator_name": operator_name,
                "entries": [
                    {
                        "target_os": entry.target_os,
                        "version": entry.version,
                        "build": entry.build,
                        "force_update": entry.force_update,
                    }
                    for entry in entries
                ],
            },
        )

        return await self.get_app_version_config()

    # ------------------------------------------------------------------ #
    async def forward_external_app_version(
        self,
        payload: ExternalAppVersionUpdateRequest,
    ) -> Dict[str, object]:
        """
        直接调用外部版本更新接口，不在本地落库。

        外部接口：
        POST {NOTIFICATION_API_URL}/app/update_version?role=write
        """
        base_url = settings.NOTIFICATION_API_URL
        if not base_url:
            raise HTTPException(status_code=500, detail="外部版本更新接口未配置")

        endpoint = f"{base_url.rstrip('/')}/app/update_version"
        body = payload.model_dump()

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    endpoint,
                    params={"role": "write"},
                    headers={
                        "accept": "application/json",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
        except Exception as exc:
            logger.exception("调用外部版本更新接口失败", extra={"endpoint": endpoint, "payload": body})
            raise HTTPException(
                status_code=502,
                detail=f"调用外部版本更新接口失败: {exc}",
            ) from exc

        try:
            data = response.json()
        except Exception:
            data = {"raw": response.text}

        if response.status_code != 200:
            logger.error(
                "外部版本更新接口返回异常",
                extra={
                    "status_code": response.status_code,
                    "response": data,
                    "payload": body,
                },
            )
            raise HTTPException(
                status_code=502,
                detail=f"外部版本更新接口返回异常状态: {response.status_code}",
            )

        return {
            "status_code": response.status_code,
            "response": data,
        }

    # ------------------------------------------------------------------ #
    async def publish_version_to_mode_api(
        self,
        payload: PublishVersionRequest,
    ) -> Dict[str, object]:
        """
        Publish a specific build to external mode API.

        External API:
        PUT {EXTERNAL_MODE_API_URL}
        Body: { "build": "...", "os": "...", "mode": "normal" }
        """
        url = settings.EXTERNAL_MODE_API_URL
        if not url:
            raise HTTPException(status_code=500, detail="External mode API URL is not configured")

        body = {
            "build": payload.build,
            "os": payload.os,
            "mode": "normal",  # mode is fixed and not exposed to client
        }

        try:
            async with httpx.AsyncClient(
                timeout=10.0,
                verify=settings.EXTERNAL_MODE_VERIFY_SSL,
            ) as client:
                response = await client.put(
                    url,
                    headers={
                        "accept": "application/json",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
        except Exception as exc:
            logger.exception("Failed to call external mode API", extra={"url": url, "payload": body})
            raise HTTPException(
                status_code=502,
                detail=f"Failed to call external mode API: {exc}",
            ) from exc

        try:
            data = response.json()
        except Exception:
            data = {"raw": response.text}

        if response.status_code < 200 or response.status_code >= 300:
            logger.error(
                "External mode API returned non-success status",
                extra={
                    "status_code": response.status_code,
                    "response": data,
                    "payload": body,
                },
            )
            raise HTTPException(
                status_code=502,
                detail=f"External mode API returned status: {response.status_code}",
            )

        return {
            "status_code": response.status_code,
            "response": data,
        }

    # ------------------------------------------------------------------ #
    def _extract_entries(self, payload: AppVersionConfigUpdateRequest) -> List["_VersionEntry"]:
        entries: List[_VersionEntry] = []
        if payload.ios:
            entries.extend(
                self._build_entries_for_platform("ios", payload.ios)
            )
        if payload.android:
            entries.extend(
                self._build_entries_for_platform("android", payload.android)
            )
        return entries

    def _build_entries_for_platform(
        self,
        platform: str,
        config: PlatformVersionUpdate,
    ) -> List["_VersionEntry"]:
        platform_entries: List[_VersionEntry] = []
        if config.optional:
            platform_entries.append(
                _VersionEntry.from_payload(platform, False, config.optional)
            )
        if config.mandatory:
            platform_entries.append(
                _VersionEntry.from_payload(platform, True, config.mandatory)
            )
        return platform_entries


class _VersionEntry:
    """Internal helper to normalize payload data."""

    def __init__(
        self,
        *,
        target_os: str,
        force_update: bool,
        payload: AppVersionUpdatePayload,
    ) -> None:
        self.target_os = target_os
        self.force_update = force_update
        self.version = payload.version
        self.build = payload.build
        self.download_url = payload.download_url
        self.release_notes = payload.release_notes
        self.release_date = payload.release_date
        self.extra = payload.extra

    @classmethod
    def from_payload(
        cls,
        target_os: str,
        force_update: bool,
        payload: AppVersionUpdatePayload,
    ) -> "_VersionEntry":
        return cls(target_os=target_os, force_update=force_update, payload=payload)

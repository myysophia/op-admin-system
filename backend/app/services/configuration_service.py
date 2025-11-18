"""Configuration service for startup modes & app versions."""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.configuration import AppVersion, StartupMode
from app.schemas.configuration import (
    AppVersionConfigResponse,
    AppVersionConfigUpdateRequest,
    AppVersionInfo,
    AppVersionUpdatePayload,
    PlatformVersionInfo,
    PlatformVersionUpdate,
    StartupModeItem,
    StartupModeListResponse,
)
from app.services.audit_service import AuditService


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
    async def get_app_version_config(self) -> AppVersionConfigResponse:
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

"""Configuration management API."""
from fastapi import APIRouter, Depends, Query

from app.auth import get_operator_context
from app.database import get_db
from app.schemas.common import Response
from app.schemas.configuration import (
    AppVersionConfigResponse,
    AppVersionConfigUpdateRequest,
    StartupModeListResponse,
)
from app.services.configuration_service import ConfigurationService

router = APIRouter()


@router.get("/startup-modes", response_model=Response[StartupModeListResponse])
async def list_startup_modes(
    mode: str | None = Query("normal", description="Startup mode filter, default normal"),
    os: str | None = Query(None, description="Filter by operating system, e.g. ios/android"),
    limit: int = Query(10, ge=1, le=100, description="Maximum records returned"),
    offset: int = Query(0, ge=0, description="Offset used for pagination"),
    db=Depends(get_db),
):
    service = ConfigurationService(db)
    data = await service.list_startup_modes(mode, os, limit, offset)
    return Response(data=data)


@router.get("/app-versions", response_model=Response[AppVersionConfigResponse])
async def get_app_versions(db=Depends(get_db)):
    service = ConfigurationService(db)
    data = await service.get_app_version_config()
    return Response(data=data)


@router.put("/app-versions", response_model=Response[AppVersionConfigResponse])
async def update_app_versions(
    payload: AppVersionConfigUpdateRequest,
    operator_ctx=Depends(get_operator_context),
    db=Depends(get_db),
):
    service = ConfigurationService(db)
    data = await service.update_app_versions(
        payload,
        operator_ctx.operator_id,
        operator_ctx.operator_name,
    )
    return Response(message="App versions updated", data=data)

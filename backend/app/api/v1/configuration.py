"""Configuration management API."""
from fastapi import APIRouter, Depends, Query

from app.auth import get_operator_context
from app.database import get_db
from app.schemas.common import Response
from app.schemas.configuration import (
    AppVersionConfigResponse,
    AppVersionConfigUpdateRequest,
    ExternalAppVersionUpdateRequest,
    PublishVersionRequest,
    StartupModeListResponse,
    StartupModeUpdateRequest,
)
from app.services.configuration_service import ConfigurationService

router = APIRouter()


@router.get("/web3-display-version", response_model=Response[StartupModeListResponse])
async def list_startup_modes(
    os: str | None = Query(None, description="Filter by operating system, e.g. ios/android"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of records returned"),
    offset: int = Query(0, ge=0, description="Number of records to skip for pagination"),
    db=Depends(get_db),
):
    """List startup modes for Web3 display configuration."""
    service = ConfigurationService(db)
    # Mode is fixed to 'normal' for this API.
    data = await service.list_startup_modes("strict", os, limit, offset)
    return Response(data=data)


@router.post(
    "/web3-display-version",
    response_model=Response[StartupModeListResponse],
)
async def create_startup_mode(
    payload: StartupModeUpdateRequest,
    operator_ctx=Depends(get_operator_context),
    db=Depends(get_db),
):
    """Create new startup mode entries for Web3 display."""
    service = ConfigurationService(db)
    data = await service.add_startup_modes(payload, operator_ctx.operator_id, operator_ctx.operator_name)
    return Response(message="Startup mode created", data=data)


@router.get(
    "/upgrade/app-versions",
    response_model=Response[AppVersionConfigResponse],
    include_in_schema=False,
)
async def get_app_versions(
    page: int = Query(1, ge=1, description="Page index (1-based)"),
    page_size: int = Query(10, ge=1, le=100, description="Page size"),
    db=Depends(get_db),
):
    """Get current app version configuration stored in this service."""
    service = ConfigurationService(db)
    # Currently pagination is not applied to the aggregated response,
    # but parameters are reserved for future extension.
    data = await service.get_app_version_config(page=page, page_size=page_size)
    return Response(data=data)


@router.put("/upgrade/app-versions", response_model=Response[AppVersionConfigResponse])
async def update_app_versions(
    payload: AppVersionConfigUpdateRequest,
    operator_ctx=Depends(get_operator_context),
    db=Depends(get_db),
):
    """Update app version configuration stored in this service."""
    service = ConfigurationService(db)
    data = await service.update_app_versions(
        payload,
        operator_ctx.operator_id,
        operator_ctx.operator_name,
    )
    return Response(message="App versions updated", data=data)


@router.post(
    "/upgrade/app-versions/forward",
    response_model=Response[dict],
    include_in_schema=False,
)
async def upgrade_app_version(
    payload: ExternalAppVersionUpdateRequest,
    operator_ctx=Depends(get_operator_context),
    db=Depends(get_db),
):
    """Forward app version payload to external upgrade API without local persistence."""
    service = ConfigurationService(db)
    data = await service.forward_external_app_version(payload)
    return Response(message="External app version updated", data=data)


@router.post(
    "/review/publish-version",
    response_model=Response[dict],
    include_in_schema=False,
)
async def publish_version(
    payload: PublishVersionRequest,
    operator_ctx=Depends(get_operator_context),
    db=Depends(get_db),
):
    """
    Publish app build/version to external mode API.

    The request body only exposes build and os to clients.
    Mode is fixed as 'normal' when calling the external API.
    """
    service = ConfigurationService(db)
    data = await service.publish_version_to_mode_api(payload)
    return Response(message="Version published to external mode API", data=data)

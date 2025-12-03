"""Operations API routes - Meme review from database (posts/pair)."""
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, Path, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas.meme import (
    MemeSearchParams,
    MemeReviewListResponse,
    MemeReviewRequest,
    MemeMockLoadRequest
)
from app.schemas.common import Response
from app.schemas.post_weight import (
    PostWeightCreateRequest,
    PostWeightCancelRequest,
    PostWeightListResponse,
    PostWeightResponse,
)
from app.services.meme_service import MemeService
from app.services.post_weight_service import PostWeightService
from app.auth import get_operator_context
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


# Meme Review Routes (from DB)
@router.get("/memes/review", response_model=Response[MemeReviewListResponse])
async def get_memes_for_review(
    user_id: Optional[str] = Query(None, description="Filter by creator user ID"),
    creator_name: Optional[str] = Query(None, description="Filter by creator display name"),
    symbol: Optional[str] = Query(None, description="Filter by meme symbol"),
    name: Optional[str] = Query(None, description="Filter by meme name"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    Get pending memes from DB (pair.status=0) for review.
    """
    params = MemeSearchParams(
        user_id=user_id,
        creator_name=creator_name,
        symbol=symbol,
        name=name,
        page=page,
        page_size=page_size
    )

    meme_service = MemeService(db)
    result = await meme_service.get_pending_memes(params)

    return Response(data=result)


@router.get("/memes/{order_id}", response_model=Response[dict])
async def get_meme_detail(
    order_id: str = Path(..., description="Meme order ID"),
    db: AsyncSession = Depends(get_db),
):
    """Get meme detail by order_id (pair.id)."""
    meme_service = MemeService(db)
    meme = await meme_service.get_meme_detail(order_id)

    return Response(data=meme)


@router.post("/memes/{order_id}/review", response_model=Response[dict])
async def review_meme(
    order_id: str = Path(..., description="Meme order ID"),
    review_data: MemeReviewRequest = None,
    operator_ctx = Depends(get_operator_context),
    db: AsyncSession = Depends(get_db),
    # operator_id: str = Depends(get_current_user),  # TODO: Add auth
):
    """
    Review meme (approve or reject) based on DB records.
    """
    meme_service = MemeService(db)
    await meme_service.review_meme(order_id, review_data, operator_ctx.operator_id)

    return Response(message=f"Meme {review_data.action}d successfully")


@router.post("/memes/sync", response_model=Response[dict])
async def sync_memes_from_kafka():
    """
    Deprecated: Kafka同步已下线，改为直接读取数据库。
    """
    raise HTTPException(status_code=410, detail="Kafka sync is disabled; review now reads from database")


@router.post("/memes/mock-load", response_model=Response[dict], include_in_schema=False)
async def load_mock_memes(
    mock_request: MemeMockLoadRequest,
):
    """
    Deprecated: Kafka mock 已下线，使用真实DB数据。
    """
    raise HTTPException(status_code=410, detail="Mock load is disabled; review now reads from database")


# Post weight management
@router.post(
    "/post-weights",
    response_model=Response[List[PostWeightResponse]],
    summary="Bulk create or update post weights",
)
async def create_post_weights(
    payload: PostWeightCreateRequest,
    operator_ctx = Depends(get_operator_context),
    db: AsyncSession = Depends(get_db),
):
    """Create or update post weights and notify recommendation service."""
    service = PostWeightService(db)
    records = await service.create_or_update(
        payload,
        operator_ctx.operator_id,
        operator_ctx.operator_name,
    )
    return Response(message="Post weights updated", data=records)


@router.get(
    "/post-weights",
    response_model=Response[PostWeightListResponse],
    summary="List post weight records",
)
async def list_post_weights(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve existing post weight configurations."""
    service = PostWeightService(db)
    result = await service.list_post_weights(page, page_size)
    return Response(message="Post weights fetched", data=result)


@router.post(
    "/post-weights/cancel",
    response_model=Response[dict],
    summary="Batch cancel post weights",
)
async def cancel_post_weights(
    payload: PostWeightCancelRequest,
    operator_ctx = Depends(get_operator_context),
    db: AsyncSession = Depends(get_db),
):
    """Cancel post weights and notify removal to recommendation service."""
    service = PostWeightService(db)
    result = await service.cancel_weights(payload.post_ids)
    return Response(message="Post weights canceled", data=result)


@router.delete(
    "/post-weights/{record_id}",
    response_model=Response[dict],
    summary="Soft delete a post weight record",
)
async def delete_post_weight(
    record_id: int = Path(..., description="Post weight record ID"),
    db: AsyncSession = Depends(get_db),
):
    """Soft delete a post weight record."""
    service = PostWeightService(db)
    await service.soft_delete(record_id)
    return Response(message="Post weight record deleted")

"""Operations API routes - Meme review from Kafka."""
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, Path, BackgroundTasks, HTTPException
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
from app.services.kafka_service import kafka_service
from app.services.post_weight_service import PostWeightService
from app.config import settings
from app.auth import get_operator_context
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


# Meme Review Routes (from Kafka)
@router.get("/memes/review", response_model=Response[MemeReviewListResponse])
async def get_memes_for_review(
    user_id: Optional[str] = Query(None, description="Filter by creator user ID"),
    symbol: Optional[str] = Query(None, description="Filter by meme symbol"),
    name: Optional[str] = Query(None, description="Filter by meme name"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    Get pending memes from Kafka queue for review.

    The memes are consumed from Kafka topic: memecoin.meme_creation
    """
    params = MemeSearchParams(
        user_id=user_id,
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
    """Get meme detail by order_id."""
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
    Review meme (approve or reject).

    - **approve**: Send to approved topic (memecoin.meme_approved)
    - **reject**: Discard the message

    The message will be removed from the review queue after processing.
    """
    meme_service = MemeService(db)
    await meme_service.review_meme(order_id, review_data, operator_ctx.operator_id)

    return Response(message=f"Meme {review_data.action}d successfully")


@router.post("/memes/sync", response_model=Response[dict])
async def sync_memes_from_kafka(
    background_tasks: BackgroundTasks,
    batch_size: int = Query(100, ge=1, le=1000, description="Number of messages to fetch")
):
    """
    Manually trigger sync from Kafka to refresh the review queue.

    This endpoint fetches new messages from Kafka and adds them to the in-memory review queue.
    In production, this should be done automatically by a background task.
    """
    try:
        # Run sync in background
        background_tasks.add_task(kafka_service.consume_messages, batch_size)

        return Response(message=f"Kafka sync triggered for up to {batch_size} messages")

    except Exception as e:
        logger.error(f"Failed to trigger Kafka sync: {e}")
        return Response(code=500, message=f"Failed to sync: {str(e)}")


@router.post("/memes/mock-load", response_model=Response[dict], include_in_schema=False)
async def load_mock_memes(
    mock_request: MemeMockLoadRequest,
):
    """
    Load mock meme messages into in-memory queue (debug only).

    This endpoint allows injecting testing data when Kafka is unavailable.
    """
    if not settings.DEBUG:
        raise HTTPException(status_code=403, detail="Mock load is disabled when DEBUG=False")

    loaded = 0
    timestamp_base = int(datetime.utcnow().timestamp() * 1000)

    for idx, meme in enumerate(mock_request.memes):
        meme_data = meme.model_dump()

        # Skip duplicates by order_id
        if kafka_service.get_meme_by_order_id(meme_data["order_id"]):
            continue

        meme_data["_kafka_offset"] = -1
        meme_data["_kafka_partition"] = 0
        meme_data["_kafka_timestamp"] = timestamp_base + idx

        kafka_service.pending_messages.append(meme_data)
        loaded += 1

    return Response(
        message=f"Mock memes loaded: {loaded}",
        data={"loaded": loaded, "requested": len(mock_request.memes)}
    )


# Post weight management
@router.post(
    "/post-weights",
    response_model=Response[List[PostWeightResponse]],
    summary="批量新增或更新帖子权重",
)
async def create_post_weights(
    payload: PostWeightCreateRequest,
    operator_ctx = Depends(get_operator_context),
    db: AsyncSession = Depends(get_db),
):
    """创建或更新帖子权重，并通知推荐系统."""
    service = PostWeightService(db)
    records = await service.create_or_update(
        payload,
        operator_ctx.operator_id,
        operator_ctx.operator_name,
    )
    return Response(message="帖子权重已更新", data=records)


@router.get(
    "/post-weights",
    response_model=Response[PostWeightListResponse],
    summary="查询帖子权重列表",
)
async def list_post_weights(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """获取帖子权重配置列表."""
    service = PostWeightService(db)
    result = await service.list_post_weights(page, page_size)
    return Response(data=result)


@router.post(
    "/post-weights/cancel",
    response_model=Response[dict],
    summary="批量取消帖子权重",
)
async def cancel_post_weights(
    payload: PostWeightCancelRequest,
    operator_ctx = Depends(get_operator_context),
    db: AsyncSession = Depends(get_db),
):
    """取消帖子权重并同步推荐系统删除接口."""
    service = PostWeightService(db)
    result = await service.cancel_weights(payload.post_ids)
    return Response(message="帖子权重已取消", data=result)


@router.delete(
    "/post-weights/{record_id}",
    response_model=Response[dict],
    summary="软删除帖子权重记录",
)
async def delete_post_weight(
    record_id: int = Path(..., description="帖子权重记录ID"),
    db: AsyncSession = Depends(get_db),
):
    """软删除帖子权重记录."""
    service = PostWeightService(db)
    await service.soft_delete(record_id)
    return Response(message="帖子权重记录已删除")

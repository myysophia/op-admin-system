"""Support API routes for会话状态管理."""
from typing import Literal

from fastapi import APIRouter, Depends, File, Path, Query, UploadFile

from app.auth import get_operator_context
from app.config import settings
from app.database import get_db
from app.schemas.common import Response
from app.schemas.support import (
    SupportConversationCreateRequest,
    SupportConversationCreateResponse,
    SupportConversationDetailResponse,
    SupportConversationListResponse,
    SupportConversationQuery,
    SupportConversationStatusUpdateRequest,
    SupportImLookupRequest,
    SupportImLookupResponse,
    SupporterListResponse,
    SupportQuickMessageCreateRequest,
    SupportQuickMessageItem,
    SupportQuickMessageListResponse,
    SupportQuickMessageUpdateRequest,
    SupportQuickMessageUploadResponse,
)
from app.services.support_service import SupportService, SupportQuickMessageService

router = APIRouter()


@router.post("/conversations", response_model=Response[SupportConversationCreateResponse])
async def create_or_update_conversation(
    payload: SupportConversationCreateRequest,
    db=Depends(get_db),
):
    """创建或刷新会话，状态默认pending。"""
    service = SupportService(db)
    result = await service.create_or_update_conversation(payload)
    return Response(message="Conversation saved", data=result)


@router.get("/conversations", response_model=Response[SupportConversationListResponse])
async def list_conversations(
    status: Literal["pending", "processed", "later"] | None = Query(None, description="pending/processed/later"),
    uid: str | None = Query(None, description="支持模糊匹配"),
    username: str | None = Query(None),
    display_name: str | None = Query(None),
    wallet_address: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db=Depends(get_db),
):
    """分页获取会话列表。"""
    query = SupportConversationQuery(
        status=status,
        uid=uid,
        username=username,
        display_name=display_name,
        wallet_address=wallet_address,
        page=page,
        page_size=page_size,
    )
    service = SupportService(db)
    data = await service.list_conversations(query)
    return Response(data=data)


@router.get(
    "/conversations/{conversation_id}",
    response_model=Response[SupportConversationDetailResponse],
)
async def get_conversation_detail(
    conversation_id: str = Path(..., description="会话ID"),
    db=Depends(get_db),
):
    """获取会话详情及用户资料。"""
    service = SupportService(db)
    detail = await service.get_conversation_detail(conversation_id)
    return Response(data=detail)


@router.post("/conversations/{conversation_id}/status", response_model=Response[dict])
async def update_conversation_status(
    conversation_id: str,
    payload: SupportConversationStatusUpdateRequest,
    operator_ctx=Depends(get_operator_context),
    db=Depends(get_db),
):
    """运营点击End/Later时更新会话状态。"""
    service = SupportService(db)
    await service.update_status(
        conversation_id,
        payload,
        operator_ctx.operator_id,
        operator_ctx.operator_name,
    )
    return Response(message="Status updated")


@router.post("/im-mapping", response_model=Response[SupportImLookupResponse])
async def lookup_users_by_im_id(
    payload: SupportImLookupRequest,
    db=Depends(get_db),
):
    """批量将 OpenIM im_id 映射为用户资料。"""
    service = SupportService(db)
    data = await service.lookup_users_by_im_ids(payload.im_ids)
    return Response(data=data)


@router.get("/supporters", response_model=Response[SupporterListResponse])
async def get_supporter_list():
    """获取客服超级管理员列表（来源于环境配置）。"""
    supporters = settings.SUPPORT_SUPER_ADMINS or []
    return Response(
        data=SupporterListResponse(supporters=supporters),
        message="Supporter list fetched",
    )


# ----------------------------- 快捷消息配置 ----------------------------- #


@router.get(
    "/quick-messages",
    response_model=Response[SupportQuickMessageListResponse],
)
async def list_quick_messages(
    active_only: bool = Query(False, description="仅返回启用的快捷消息"),
    db=Depends(get_db),
):
    service = SupportQuickMessageService(db)
    data = await service.list_quick_messages(active_only)
    return Response(data=data)


@router.post(
    "/quick-messages",
    response_model=Response[SupportQuickMessageItem],
)
async def create_quick_message(
    payload: SupportQuickMessageCreateRequest,
    operator_ctx=Depends(get_operator_context),
    db=Depends(get_db),
):
    service = SupportQuickMessageService(db)
    item = await service.create_quick_message(payload, operator_ctx.operator_id)
    return Response(message="Quick message created", data=item)


@router.put(
    "/quick-messages/{message_id}",
    response_model=Response[SupportQuickMessageItem],
)
async def update_quick_message(
    message_id: str,
    payload: SupportQuickMessageUpdateRequest,
    operator_ctx=Depends(get_operator_context),
    db=Depends(get_db),
):
    service = SupportQuickMessageService(db)
    item = await service.update_quick_message(message_id, payload, operator_ctx.operator_id)
    return Response(message="Quick message updated", data=item)


@router.delete(
    "/quick-messages/{message_id}",
    response_model=Response[dict],
)
async def delete_quick_message(
    message_id: str,
    operator_ctx=Depends(get_operator_context),
    db=Depends(get_db),
):
    service = SupportQuickMessageService(db)
    await service.delete_quick_message(message_id, operator_ctx.operator_id)
    return Response(message="Quick message deleted", data={})


@router.post(
    "/quick-messages/upload",
    response_model=Response[SupportQuickMessageUploadResponse],
)
async def upload_quick_message_image(
    file: UploadFile = File(..., description="图片文件"),
    operator_ctx=Depends(get_operator_context),
    db=Depends(get_db),
):
    data = await file.read()
    service = SupportQuickMessageService(db)
    result = await service.upload_image(
        operator_id=operator_ctx.operator_id,
        filename=file.filename,
        content_type=file.content_type,
        data=data,
    )
    return Response(message="Image uploaded", data=result)

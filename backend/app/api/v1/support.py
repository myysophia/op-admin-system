"""Support API routes for conversation state management."""
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
    SupportCaseCreateRequest,
    SupportCaseUpdateRequest,
    SupportCaseListResponse,
    SupportCaseItem,
)
from app.services.support_service import SupportService, SupportQuickMessageService

router = APIRouter()


# ----------------------------- Chat list & status ----------------------------- #


@router.get(
    "/chats",
    response_model=Response[SupportConversationListResponse],
    summary="List chats (OpenIM + local status)",
    include_in_schema=False,
)
async def list_chat_sessions(
    status: Literal["pending", "processed"] | None = Query(None, description="Filter by status"),
    uid: str | None = Query(None, description="Fuzzy user id"),
    username: str | None = Query(None),
    display_name: str | None = Query(None),
    wallet_address: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db=Depends(get_db),
):
    """Fetch OpenIM conversation list, merge local status, return list + status only."""
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


@router.patch(
    "/chats/{conversation_id}/status",
    response_model=Response[dict],
    summary="Update chat status (pending/processed)",
    include_in_schema=False,
)
async def patch_chat_status(
    conversation_id: str,
    payload: SupportConversationStatusUpdateRequest,
    operator_ctx=Depends(get_operator_context),
    db=Depends(get_db),
):
    """Update local chat status only; no message persistence."""
    service = SupportService(db)
    await service.update_status(
        conversation_id,
        payload,
        operator_ctx.operator_id,
        operator_ctx.operator_name,
    )
    return Response(message="Status updated")


# ----------------------------- Support Cases ----------------------------- #


@router.post(
    "/cases",
    response_model=Response[SupportCaseItem],
)
async def create_support_case(
    payload: SupportCaseCreateRequest,
    db=Depends(get_db),
):
    service = SupportService(db)
    item = await service.create_case(payload)
    return Response(message="Support case created", data=item)


@router.get(
    "/cases",
    response_model=Response[SupportCaseListResponse],
)
async def list_support_cases(
    status: str | None = Query(None, description="Filter by status, e.g. open/closed"),
    user_id: str | None = Query(None, description="Filter by user id"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db=Depends(get_db),
):
    service = SupportService(db)
    data = await service.list_cases(page=page, page_size=page_size, status=status, user_id=user_id)
    return Response(data=data)


@router.get(
    "/cases/{case_id}",
    response_model=Response[SupportCaseItem],
)
async def get_support_case(
    case_id: str,
    db=Depends(get_db),
):
    service = SupportService(db)
    item = await service.get_case(case_id)
    return Response(data=item)


@router.put(
    "/cases/{case_id}",
    response_model=Response[SupportCaseItem],
)
async def update_support_case(
    case_id: str,
    payload: SupportCaseUpdateRequest,
    db=Depends(get_db),
):
    service = SupportService(db)
    item = await service.update_case(case_id, payload)
    return Response(message="Support case updated", data=item)


@router.delete(
    "/cases/{case_id}",
    response_model=Response[dict],
)
async def delete_support_case(
    case_id: str,
    db=Depends(get_db),
):
    service = SupportService(db)
    await service.delete_case(case_id)
    return Response(message="Support case deleted", data={})


@router.post(
    "/conversations",
    response_model=Response[SupportConversationCreateResponse],
    include_in_schema=False,
)
async def create_or_update_conversation(
    payload: SupportConversationCreateRequest,
    db=Depends(get_db),
):
    """创建或刷新会话，状态默认pending。"""
    service = SupportService(db)
    result = await service.create_or_update_conversation(payload)
    return Response(message="Conversation saved", data=result)


@router.get(
    "/conversations",
    response_model=Response[SupportConversationListResponse],
    include_in_schema=False,
)
async def list_conversations(
    status: Literal["pending", "processed"] | None = Query(None, description="pending/processed"),
    uid: str | None = Query(None, description="Fuzzy user id"),
    username: str | None = Query(None),
    display_name: str | None = Query(None),
    wallet_address: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db=Depends(get_db),
):
    """List conversations with pagination."""
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
    include_in_schema=False,
)
async def get_conversation_detail(
    conversation_id: str = Path(..., description="Conversation ID"),
    db=Depends(get_db),
):
    """Get conversation detail and user profile."""
    service = SupportService(db)
    detail = await service.get_conversation_detail(conversation_id)
    return Response(data=detail)


@router.post(
    "/conversations/{conversation_id}/status",
    response_model=Response[dict],
    include_in_schema=False,
)
async def update_conversation_status(
    conversation_id: str,
    payload: SupportConversationStatusUpdateRequest,
    operator_ctx=Depends(get_operator_context),
    db=Depends(get_db),
):
    """Update conversation status when operator clicks End/Later."""
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
    """Batch map OpenIM im_id to user profiles."""
    service = SupportService(db)
    data = await service.lookup_users_by_im_ids(payload.im_ids)
    return Response(data=data)


@router.get("/supporters", response_model=Response[SupporterListResponse])
async def get_supporter_list():
    """Get supporter admin list from config."""
    supporters = settings.SUPPORT_SUPER_ADMINS or []
    return Response(
        data=SupporterListResponse(supporters=supporters),
        message="Supporter list fetched",
    )


# ----------------------------- Quick messages ----------------------------- #


@router.get(
    "/quick-messages",
    response_model=Response[SupportQuickMessageListResponse],
)
async def list_quick_messages(
    active_only: bool = Query(False, description="Return enabled quick messages only"),
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
    file: UploadFile = File(..., description="Image file"),
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

"""Support API routes - simplified (OpenIM handles real-time messaging)."""
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, Path, Body
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas.support import (
    ConversationListResponse,
    ConversationDetailResponse,
    ConversationSearchParams,
    ConversationResponse,
    AssignConversationRequest,
    UpdateConversationStatusRequest,
    SendMessageRequest,
    BatchSendMessageRequest,
    BatchSendMessageResponse,
    QuickReplyCreate,
    QuickReplyUpdate,
    QuickReplyResponse,
    QuickReplyListResponse
)
from app.schemas.common import Response
from app.services.support_service import SupportService
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


# Conversation Routes
@router.get("/conversations", response_model=Response[ConversationListResponse])
async def get_conversations(
    status: Optional[str] = Query(None, description="pending, in_progress, later, ended"),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    has_unread: Optional[bool] = Query(None, description="Filter by unread status"),
    sort_by: str = Query("priority", description="Sort by: priority, last_message_at, created_at, unread_count"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    # operator_id: str = Depends(get_current_user),  # TODO: Add auth
):
    """
    Get support conversation list.

    Status filtering:
    - pending: New conversations + later conversations with new messages
    - in_progress: Being handled by operator
    - later: Marked for later follow-up (no new messages)
    - ended: Closed conversations
    """
    operator_id = "admin"  # TODO: Get from auth

    params = ConversationSearchParams(
        status=status,
        user_id=user_id,
        has_unread=has_unread,
        sort_by=sort_by,
        page=page,
        page_size=page_size
    )

    support_service = SupportService(db)
    result = await support_service.get_conversations(params, operator_id=operator_id)

    return Response(data=result)


@router.get("/conversations/{conversation_id}", response_model=Response[ConversationDetailResponse])
async def get_conversation_detail(
    conversation_id: str = Path(..., description="Conversation ID"),
    db: AsyncSession = Depends(get_db),
    # operator_id: str = Depends(get_current_user),  # TODO: Add auth
):
    """
    Get conversation detail with messages from OpenIM.

    Returns conversation info and message history.
    Automatically marks conversation as read for operator.
    """
    operator_id = "admin"  # TODO: Get from auth

    support_service = SupportService(db)
    result = await support_service.get_conversation_detail(conversation_id, operator_id)

    return Response(data=result)


@router.post("/conversations/{conversation_id}/assign", response_model=Response[ConversationResponse])
async def assign_conversation(
    conversation_id: str = Path(..., description="Conversation ID"),
    request: AssignConversationRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    # operator_id: str = Depends(get_current_user),  # TODO: Add auth
):
    """
    Assign conversation to operator.

    Changes status to 'in_progress'.
    """
    operator_id = "admin"  # TODO: Get from auth

    support_service = SupportService(db)
    conv = await support_service.assign_conversation(conversation_id, request.operator_id)

    return Response(
        message="Conversation assigned successfully",
        data=ConversationResponse.model_validate(conv)
    )


@router.post("/conversations/{conversation_id}/status", response_model=Response[ConversationResponse])
async def update_conversation_status(
    conversation_id: str = Path(..., description="Conversation ID"),
    request: UpdateConversationStatusRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    # operator_id: str = Depends(get_current_user),  # TODO: Add auth
):
    """
    Update conversation status.

    Supported status transitions:
    - later: Mark for later follow-up (稍后回复)
    - ended: Close conversation (结束对话)
    - in_progress: Reopen conversation
    """
    operator_id = "admin"  # TODO: Get from auth

    support_service = SupportService(db)
    conv = await support_service.update_conversation_status(
        conversation_id,
        request.status,
        operator_id
    )

    return Response(
        message=f"Conversation status updated to {request.status}",
        data=ConversationResponse.model_validate(conv)
    )


# Message Routes (via OpenIM)
@router.post("/conversations/{conversation_id}/messages", response_model=Response[dict])
async def send_message(
    conversation_id: str = Path(..., description="Conversation ID"),
    message: SendMessageRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    # operator_id: str = Depends(get_current_user),  # TODO: Add auth
):
    """
    Send message to user in conversation via OpenIM.

    The message is sent through OpenIM server, ensuring real-time delivery.
    """
    operator_id = "admin"  # TODO: Get from auth

    support_service = SupportService(db)
    success = await support_service.send_message(conversation_id, message, operator_id)

    if success:
        return Response(message="Message sent successfully")
    else:
        return Response(code=500, message="Failed to send message")


@router.post("/conversations/batch-message", response_model=Response[BatchSendMessageResponse])
async def batch_send_message(
    batch_request: BatchSendMessageRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    # operator_id: str = Depends(get_current_user),  # TODO: Add auth
):
    """
    Send same message to multiple conversations (batch reply).

    Useful for sending announcements or similar responses to multiple users.
    """
    operator_id = "admin"  # TODO: Get from auth

    support_service = SupportService(db)
    result = await support_service.batch_send_message(batch_request, operator_id)

    return Response(
        message=f"Batch message sent: {result['success']}/{result['total']} successful",
        data=BatchSendMessageResponse(**result)
    )


# Quick Reply Routes
@router.get("/quick-replies", response_model=Response[QuickReplyListResponse])
async def get_quick_replies(
    include_shared: bool = Query(True, description="Include shared quick replies"),
    db: AsyncSession = Depends(get_db),
    # operator_id: str = Depends(get_current_user),  # TODO: Add auth
):
    """
    Get quick reply templates for operator.

    Returns operator's own templates and optionally shared templates from other operators.
    """
    operator_id = "admin"  # TODO: Get from auth

    support_service = SupportService(db)
    replies = await support_service.get_quick_replies(operator_id, include_shared)

    return Response(data=QuickReplyListResponse(items=replies, total=len(replies)))


@router.post("/quick-replies", response_model=Response[QuickReplyResponse])
async def create_quick_reply(
    reply_data: QuickReplyCreate = Body(...),
    db: AsyncSession = Depends(get_db),
    # operator_id: str = Depends(get_current_user),  # TODO: Add auth
):
    """
    Create new quick reply template.

    Can be marked as shared for other operators to use.
    """
    operator_id = "admin"  # TODO: Get from auth

    support_service = SupportService(db)
    reply = await support_service.create_quick_reply(reply_data, operator_id)

    return Response(
        message="Quick reply created successfully",
        data=QuickReplyResponse.model_validate(reply)
    )


@router.put("/quick-replies/{reply_id}", response_model=Response[QuickReplyResponse])
async def update_quick_reply(
    reply_id: int = Path(..., description="Quick reply ID"),
    reply_data: QuickReplyUpdate = Body(...),
    db: AsyncSession = Depends(get_db),
    # operator_id: str = Depends(get_current_user),  # TODO: Add auth
):
    """Update quick reply template."""
    operator_id = "admin"  # TODO: Get from auth

    support_service = SupportService(db)
    reply = await support_service.update_quick_reply(reply_id, reply_data, operator_id)

    return Response(
        message="Quick reply updated successfully",
        data=QuickReplyResponse.model_validate(reply)
    )


@router.delete("/quick-replies/{reply_id}", response_model=Response[dict])
async def delete_quick_reply(
    reply_id: int = Path(..., description="Quick reply ID"),
    db: AsyncSession = Depends(get_db),
    # operator_id: str = Depends(get_current_user),  # TODO: Add auth
):
    """Delete quick reply template."""
    operator_id = "admin"  # TODO: Get from auth

    support_service = SupportService(db)
    await support_service.delete_quick_reply(reply_id, operator_id)

    return Response(message="Quick reply deleted successfully")


@router.post("/quick-replies/{reply_id}/use", response_model=Response[dict])
async def use_quick_reply(
    reply_id: int = Path(..., description="Quick reply ID"),
    db: AsyncSession = Depends(get_db),
):
    """
    Increment usage count for quick reply.

    Called when operator uses this quick reply template.
    """
    support_service = SupportService(db)
    await support_service.increment_quick_reply_usage(reply_id)

    return Response(message="Usage count incremented")

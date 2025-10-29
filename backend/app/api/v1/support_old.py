"""Support API routes."""
from typing import Optional
from fastapi import APIRouter, Depends, Query, Path, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas.support import (
    ConversationResponse,
    ConversationListResponse,
    ConversationDetailResponse,
    ConversationSearchParams,
    MessageCreate,
    MessageResponse,
    QuickReplyCreate,
    QuickReplyUpdate,
    QuickReplyResponse,
)
from app.schemas.common import Response
from app.services.support_service import SupportService
from app.services.websocket_service import WebSocketManager
import logging

router = APIRouter()
logger = logging.getLogger(__name__)
ws_manager = WebSocketManager()


# Conversation Routes
@router.get("/conversations", response_model=Response[ConversationListResponse])
async def get_conversations(
    status: str = Query("pending"),
    uid: Optional[str] = Query(None),
    username: Optional[str] = Query(None),
    displayname: Optional[str] = Query(None),
    wallet_address: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get support conversation list."""
    params = ConversationSearchParams(
        status=status,
        uid=uid,
        username=username,
        displayname=displayname,
        wallet_address=wallet_address,
        page=page,
        page_size=page_size
    )

    support_service = SupportService(db)
    result = await support_service.get_conversations(params)

    return Response(data=result)


@router.get("/conversations/{conversation_id}", response_model=Response[ConversationDetailResponse])
async def get_conversation_detail(
    conversation_id: str = Path(..., description="Conversation ID"),
    db: AsyncSession = Depends(get_db),
):
    """Get conversation detail with messages."""
    support_service = SupportService(db)
    result = await support_service.get_conversation_detail(conversation_id)

    return Response(data=result)


@router.post("/conversations/{conversation_id}/assign", response_model=Response[dict])
async def assign_conversation(
    conversation_id: str = Path(..., description="Conversation ID"),
    db: AsyncSession = Depends(get_db),
    # operator_id: int = Depends(get_current_user),  # TODO: Add auth
):
    """Assign conversation to operator (open conversation)."""
    operator_id = 1  # TODO: Get from auth

    support_service = SupportService(db)
    await support_service.assign_conversation(conversation_id, operator_id)

    return Response(message="Conversation assigned successfully")


@router.post("/conversations/{conversation_id}/release", response_model=Response[dict])
async def release_conversation(
    conversation_id: str = Path(..., description="Conversation ID"),
    db: AsyncSession = Depends(get_db),
    # operator_id: int = Depends(get_current_user),  # TODO: Add auth
):
    """Release conversation (handle later)."""
    operator_id = 1  # TODO: Get from auth

    support_service = SupportService(db)
    await support_service.release_conversation(conversation_id, operator_id)

    return Response(message="Conversation released")


@router.post("/conversations/{conversation_id}/close", response_model=Response[dict])
async def close_conversation(
    conversation_id: str = Path(..., description="Conversation ID"),
    db: AsyncSession = Depends(get_db),
    # operator_id: int = Depends(get_current_user),  # TODO: Add auth
):
    """Close conversation (mark as processed)."""
    operator_id = 1  # TODO: Get from auth

    support_service = SupportService(db)
    await support_service.close_conversation(conversation_id, operator_id)

    return Response(message="Conversation closed")


@router.post("/conversations/{conversation_id}/messages", response_model=Response[MessageResponse])
async def send_message(
    conversation_id: str = Path(..., description="Conversation ID"),
    message_data: MessageCreate = None,
    db: AsyncSession = Depends(get_db),
    # operator_id: int = Depends(get_current_user),  # TODO: Add auth
):
    """Send message in conversation."""
    operator_id = 1  # TODO: Get from auth

    support_service = SupportService(db)
    message = await support_service.send_message(conversation_id, message_data, operator_id)

    # Notify via WebSocket
    await ws_manager.broadcast_message(conversation_id, {
        "type": "new_message",
        "data": {
            "conversation_id": conversation_id,
            "message": message.dict()
        }
    })

    return Response(data=message, message="Message sent successfully")


# Quick Reply Routes
@router.get("/quick-replies", response_model=Response[list[QuickReplyResponse]])
async def get_quick_replies(
    db: AsyncSession = Depends(get_db),
    # operator_id: int = Depends(get_current_user),  # TODO: Add auth
):
    """Get quick reply templates."""
    operator_id = 1  # TODO: Get from auth

    support_service = SupportService(db)
    replies = await support_service.get_quick_replies(operator_id)

    return Response(data=replies)


@router.post("/quick-replies", response_model=Response[QuickReplyResponse])
async def create_quick_reply(
    reply_data: QuickReplyCreate = None,
    db: AsyncSession = Depends(get_db),
    # operator_id: int = Depends(get_current_user),  # TODO: Add auth
):
    """Create quick reply template."""
    operator_id = 1  # TODO: Get from auth

    support_service = SupportService(db)
    reply = await support_service.create_quick_reply(reply_data, operator_id)

    return Response(data=reply, message="Quick reply created successfully")


@router.put("/quick-replies/{reply_id}", response_model=Response[QuickReplyResponse])
async def update_quick_reply(
    reply_id: int = Path(..., description="Quick reply ID"),
    reply_data: QuickReplyUpdate = None,
    db: AsyncSession = Depends(get_db),
):
    """Update quick reply template."""
    support_service = SupportService(db)
    reply = await support_service.update_quick_reply(reply_id, reply_data)

    return Response(data=reply, message="Quick reply updated successfully")


@router.delete("/quick-replies/{reply_id}", response_model=Response[dict])
async def delete_quick_reply(
    reply_id: int = Path(..., description="Quick reply ID"),
    db: AsyncSession = Depends(get_db),
):
    """Delete quick reply template."""
    support_service = SupportService(db)
    await support_service.delete_quick_reply(reply_id)

    return Response(message="Quick reply deleted successfully")


# WebSocket endpoint
@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    # operator_id: int = Query(...),  # TODO: Add auth
):
    """WebSocket endpoint for real-time support chat."""
    operator_id = 1  # TODO: Get from auth

    await ws_manager.connect(websocket, operator_id)

    try:
        while True:
            data = await websocket.receive_json()
            logger.info(f"Received WebSocket message: {data}")

            # Handle different message types
            if data.get("type") == "subscribe":
                conversation_id = data.get("conversation_id")
                await ws_manager.subscribe(operator_id, conversation_id)

            elif data.get("type") == "unsubscribe":
                conversation_id = data.get("conversation_id")
                await ws_manager.unsubscribe(operator_id, conversation_id)

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: operator_id={operator_id}")
        await ws_manager.disconnect(operator_id)
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        await ws_manager.disconnect(operator_id)

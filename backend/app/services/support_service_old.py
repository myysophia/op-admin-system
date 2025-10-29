"""Support service layer."""
from datetime import datetime
from typing import List
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from app.models.support import SupportConversation, SupportMessage, QuickReply
from app.schemas.support import (
    ConversationSearchParams,
    ConversationListResponse,
    ConversationDetailResponse,
    ConversationResponse,
    MessageCreate,
    MessageResponse,
    QuickReplyCreate,
    QuickReplyUpdate,
    QuickReplyResponse
)
from app.services.openim_service import OpenIMService
import uuid


class SupportService:
    """Support service."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.openim_service = OpenIMService()

    async def get_conversations(
        self,
        params: ConversationSearchParams
    ) -> ConversationListResponse:
        """Get conversation list with search and pagination."""
        # Build query
        query = select(SupportConversation)

        # Apply filters
        filters = [SupportConversation.status == params.status] if params.status else []

        if params.uid:
            filters.append(SupportConversation.user_uid == int(params.uid))
        if params.username:
            filters.append(SupportConversation.user_username.ilike(f"%{params.username}%"))
        if params.displayname:
            filters.append(SupportConversation.user_displayname.ilike(f"%{params.displayname}%"))
        if params.wallet_address:
            filters.append(SupportConversation.user_wallet_address.ilike(f"%{params.wallet_address}%"))

        if filters:
            query = query.where(and_(*filters))

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total = await self.db.scalar(count_query)

        # Apply sorting (by updated_at desc for pending, by last_message_time for others)
        query = query.order_by(SupportConversation.updated_at.desc())

        # Apply pagination
        offset = (params.page - 1) * params.page_size
        query = query.offset(offset).limit(params.page_size)

        # Execute query
        result = await self.db.execute(query)
        conversations = result.scalars().all()

        return ConversationListResponse(
            items=[ConversationResponse.model_validate(conv) for conv in conversations],
            total=total or 0,
            page=params.page,
            page_size=params.page_size
        )

    async def get_conversation_detail(
        self,
        conversation_id: str
    ) -> ConversationDetailResponse:
        """Get conversation detail with messages."""
        # Get conversation
        conv_query = select(SupportConversation).where(
            SupportConversation.conversation_id == conversation_id
        )
        conv_result = await self.db.execute(conv_query)
        conversation = conv_result.scalar_one_or_none()

        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        # Get messages
        msg_query = select(SupportMessage).where(
            SupportMessage.conversation_id == conversation_id
        ).order_by(SupportMessage.created_at.asc())

        msg_result = await self.db.execute(msg_query)
        messages = msg_result.scalars().all()

        # Mark messages as read
        for msg in messages:
            if not msg.is_read and msg.sender_type == "user":
                msg.is_read = True

        conversation.unread_count = 0
        conversation.has_new_message = False
        await self.db.commit()

        return ConversationDetailResponse(
            conversation=ConversationResponse.model_validate(conversation),
            messages=[MessageResponse.model_validate(msg) for msg in messages]
        )

    async def assign_conversation(
        self,
        conversation_id: str,
        operator_id: int
    ) -> None:
        """Assign conversation to operator (lock conversation)."""
        # Get conversation
        query = select(SupportConversation).where(
            SupportConversation.conversation_id == conversation_id
        )
        result = await self.db.execute(query)
        conversation = result.scalar_one_or_none()

        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        # Check if already assigned to another operator
        if conversation.assigned_operator_id and conversation.assigned_operator_id != operator_id:
            if conversation.status == "processing":
                raise HTTPException(
                    status_code=400,
                    detail="Conversation is already being handled by another operator"
                )

        # Assign to operator
        conversation.assigned_operator_id = operator_id
        conversation.assigned_at = datetime.utcnow()
        conversation.status = "processing"
        conversation.updated_at = datetime.utcnow()

        await self.db.commit()

    async def release_conversation(
        self,
        conversation_id: str,
        operator_id: int
    ) -> None:
        """Release conversation (handle later)."""
        # Get conversation
        query = select(SupportConversation).where(
            SupportConversation.conversation_id == conversation_id
        )
        result = await self.db.execute(query)
        conversation = result.scalar_one_or_none()

        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        # Check ownership
        if conversation.assigned_operator_id != operator_id:
            raise HTTPException(
                status_code=403,
                detail="Not authorized to release this conversation"
            )

        # Release
        conversation.assigned_operator_id = None
        conversation.assigned_at = None
        conversation.status = "pending"
        conversation.updated_at = datetime.utcnow()

        await self.db.commit()

    async def close_conversation(
        self,
        conversation_id: str,
        operator_id: int
    ) -> None:
        """Close conversation (mark as processed)."""
        # Get conversation
        query = select(SupportConversation).where(
            SupportConversation.conversation_id == conversation_id
        )
        result = await self.db.execute(query)
        conversation = result.scalar_one_or_none()

        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        # Check ownership
        if conversation.assigned_operator_id != operator_id:
            raise HTTPException(
                status_code=403,
                detail="Not authorized to close this conversation"
            )

        # Close
        conversation.status = "processed"
        conversation.updated_at = datetime.utcnow()

        await self.db.commit()

    async def send_message(
        self,
        conversation_id: str,
        message_data: MessageCreate,
        operator_id: int
    ) -> MessageResponse:
        """Send message in conversation."""
        # Get conversation
        conv_query = select(SupportConversation).where(
            SupportConversation.conversation_id == conversation_id
        )
        conv_result = await self.db.execute(conv_query)
        conversation = conv_result.scalar_one_or_none()

        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        # Create message
        message_id = f"msg_{uuid.uuid4().hex}"
        message = SupportMessage(
            conversation_id=conversation_id,
            message_id=message_id,
            sender_uid=operator_id,
            sender_type="operator",
            content_type=message_data.content_type,
            content=message_data.content,
            is_read=True
        )

        self.db.add(message)

        # Update conversation
        conversation.last_message_content = message_data.content
        conversation.last_message_time = datetime.utcnow()
        conversation.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(message)

        # Send via OpenIM
        # TODO: Get user's IM ID and send message
        # await self.openim_service.send_message(
        #     to_user_id=conversation.user_uid,
        #     content=message_data.content
        # )

        return MessageResponse.model_validate(message)

    # Quick Reply Methods
    async def get_quick_replies(self, operator_id: int) -> List[QuickReplyResponse]:
        """Get quick reply templates for operator."""
        query = select(QuickReply).where(
            or_(
                QuickReply.operator_id == operator_id,
                QuickReply.is_shared == True
            )
        ).order_by(QuickReply.usage_count.desc(), QuickReply.created_at.desc())

        result = await self.db.execute(query)
        replies = result.scalars().all()

        return [QuickReplyResponse.model_validate(reply) for reply in replies]

    async def create_quick_reply(
        self,
        reply_data: QuickReplyCreate,
        operator_id: int
    ) -> QuickReplyResponse:
        """Create quick reply template."""
        reply = QuickReply(
            operator_id=operator_id,
            title=reply_data.title,
            content=reply_data.content,
            is_shared=reply_data.is_shared,
            usage_count=0
        )

        self.db.add(reply)
        await self.db.commit()
        await self.db.refresh(reply)

        return QuickReplyResponse.model_validate(reply)

    async def update_quick_reply(
        self,
        reply_id: int,
        reply_data: QuickReplyUpdate
    ) -> QuickReplyResponse:
        """Update quick reply template."""
        query = select(QuickReply).where(QuickReply.id == reply_id)
        result = await self.db.execute(query)
        reply = result.scalar_one_or_none()

        if not reply:
            raise HTTPException(status_code=404, detail="Quick reply not found")

        # Update fields
        update_data = reply_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(reply, field, value)

        reply.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(reply)

        return QuickReplyResponse.model_validate(reply)

    async def delete_quick_reply(self, reply_id: int) -> None:
        """Delete quick reply template."""
        query = select(QuickReply).where(QuickReply.id == reply_id)
        result = await self.db.execute(query)
        reply = result.scalar_one_or_none()

        if not reply:
            raise HTTPException(status_code=404, detail="Quick reply not found")

        await self.db.delete(reply)
        await self.db.commit()

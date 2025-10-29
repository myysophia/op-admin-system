"""Support service layer - chat support with OpenIM integration."""
from datetime import datetime
from typing import Optional, List
from sqlalchemy import select, and_, or_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from fastapi import HTTPException
from app.models.support import SupportConversation, QuickReply
from app.models.user import User, Author
from app.schemas.support import (
    ConversationSearchParams,
    ConversationListResponse,
    ConversationDetailResponse,
    ConversationResponse,
    SendMessageRequest,
    BatchSendMessageRequest,
    QuickReplyCreate,
    QuickReplyUpdate,
    QuickReplyResponse
)
from app.services.openim_service import openim_service
from app.services.audit_service import AuditService
import uuid
import logging

logger = logging.getLogger(__name__)


class SupportService:
    """Support service for customer service chat."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.openim_service = openim_service
        self.audit_service = AuditService(db)

    async def get_conversations(
        self,
        params: ConversationSearchParams,
        operator_id: Optional[str] = None
    ) -> ConversationListResponse:
        """
        Get conversations list with filters.

        Args:
            params: Search parameters
            operator_id: Filter by assigned operator (optional)

        Returns:
            Paginated conversation list
        """
        query = select(SupportConversation).options(
            selectinload(SupportConversation.user).selectinload(User.author),
            selectinload(SupportConversation.operator).selectinload(User.author)
        )

        # Apply filters
        filters = []

        if params.status:
            if params.status == "pending":
                # Pending includes: pending + later with unread messages
                filters.append(
                    or_(
                        SupportConversation.status == "pending",
                        and_(
                            SupportConversation.status == "later",
                            SupportConversation.has_unread_messages == True
                        )
                    )
                )
            elif params.status == "later":
                # Later without new messages
                filters.append(
                    and_(
                        SupportConversation.status == "later",
                        SupportConversation.has_unread_messages == False
                    )
                )
            elif params.status == "ended":
                filters.append(SupportConversation.status == "ended")
            elif params.status == "in_progress":
                filters.append(SupportConversation.status == "in_progress")

        if operator_id:
            filters.append(SupportConversation.operator_id == operator_id)

        if params.user_id:
            filters.append(SupportConversation.user_id.ilike(f"%{params.user_id}%"))

        if params.has_unread is not None:
            filters.append(SupportConversation.has_unread_messages == params.has_unread)

        if filters:
            query = query.where(and_(*filters))

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total = await self.db.scalar(count_query) or 0

        # Apply sorting
        if params.sort_by == "last_message_at":
            query = query.order_by(desc(SupportConversation.last_message_at))
        elif params.sort_by == "created_at":
            query = query.order_by(desc(SupportConversation.created_at))
        elif params.sort_by == "unread_count":
            query = query.order_by(desc(SupportConversation.unread_count))
        else:
            # Default: prioritize unread, then by last message time
            query = query.order_by(
                desc(SupportConversation.has_unread_messages),
                desc(SupportConversation.last_message_at)
            )

        # Apply pagination
        offset = (params.page - 1) * params.page_size
        query = query.offset(offset).limit(params.page_size)

        # Execute query
        result = await self.db.execute(query)
        conversations = result.scalars().all()

        # Build response
        items = []
        for conv in conversations:
            # Get user info
            user_info = None
            if conv.user and conv.user.author:
                user_info = {
                    "user_id": conv.user.id,
                    "username": conv.user.author.username,
                    "name": conv.user.author.name,
                    "avatar": conv.user.author.avatar
                }

            # Get operator info
            operator_info = None
            if conv.operator and conv.operator.author:
                operator_info = {
                    "operator_id": conv.operator.id,
                    "username": conv.operator.author.username,
                    "name": conv.operator.author.name
                }

            item = ConversationResponse(
                id=conv.id,
                user_id=conv.user_id,
                operator_id=conv.operator_id,
                status=conv.status,
                openim_conversation_id=conv.openim_conversation_id,
                has_unread_messages=conv.has_unread_messages,
                unread_count=conv.unread_count,
                last_message_at=conv.last_message_at,
                last_message_from=conv.last_message_from,
                last_message_preview=conv.last_message_preview,
                resolved_at=conv.resolved_at,
                created_at=conv.created_at,
                user_info=user_info,
                operator_info=operator_info
            )
            items.append(item)

        return ConversationListResponse(
            items=items,
            total=total,
            page=params.page,
            page_size=params.page_size
        )

    async def get_conversation_detail(
        self,
        conversation_id: str,
        operator_id: str
    ) -> ConversationDetailResponse:
        """
        Get conversation detail with messages from OpenIM.

        Args:
            conversation_id: Conversation ID
            operator_id: Operator user ID

        Returns:
            Conversation detail with messages
        """
        # Get conversation from DB
        query = select(SupportConversation).options(
            selectinload(SupportConversation.user).selectinload(User.author),
            selectinload(SupportConversation.operator)
        ).where(SupportConversation.id == conversation_id)

        result = await self.db.execute(query)
        conv = result.scalar_one_or_none()

        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

        # Get OpenIM conversation ID
        if not conv.openim_conversation_id:
            # Create OpenIM conversation ID
            conv.openim_conversation_id = self.openim_service.get_conversation_id(
                operator_id, conv.user_id
            )
            await self.db.commit()

        # Get messages from OpenIM
        messages = []
        try:
            messages = await self.openim_service.get_conversation_messages(
                user_id=operator_id,
                conversation_id=conv.openim_conversation_id,
                limit=100
            )
        except Exception as e:
            logger.error(f"Failed to fetch OpenIM messages: {e}")

        # Mark conversation as read for operator
        if conv.has_unread_messages:
            conv.has_unread_messages = False
            conv.unread_count = 0
            await self.db.commit()

        # Build user info
        user_info = None
        if conv.user and conv.user.author:
            user_info = {
                "user_id": conv.user.id,
                "username": conv.user.author.username,
                "name": conv.user.author.name,
                "avatar": conv.user.author.avatar
            }

        return ConversationDetailResponse(
            id=conv.id,
            user_id=conv.user_id,
            operator_id=conv.operator_id,
            status=conv.status,
            openim_conversation_id=conv.openim_conversation_id,
            last_message_at=conv.last_message_at,
            resolved_at=conv.resolved_at,
            created_at=conv.created_at,
            user_info=user_info,
            messages=messages
        )

    async def assign_conversation(
        self,
        conversation_id: str,
        operator_id: str
    ) -> SupportConversation:
        """Assign conversation to operator."""
        query = select(SupportConversation).where(
            SupportConversation.id == conversation_id
        )
        result = await self.db.execute(query)
        conv = result.scalar_one_or_none()

        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

        conv.operator_id = operator_id
        conv.status = "in_progress"
        conv.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(conv)

        # Audit log
        await self.audit_service.log_action(
            operator_id=operator_id,
            action_type="assign_conversation",
            target_type="conversation",
            target_id=conversation_id,
            action_details={"user_id": conv.user_id}
        )

        return conv

    async def update_conversation_status(
        self,
        conversation_id: str,
        status: str,
        operator_id: str
    ) -> SupportConversation:
        """Update conversation status (later / ended)."""
        if status not in ["later", "ended", "in_progress"]:
            raise HTTPException(
                status_code=400,
                detail="Status must be 'later', 'ended', or 'in_progress'"
            )

        query = select(SupportConversation).where(
            SupportConversation.id == conversation_id
        )
        result = await self.db.execute(query)
        conv = result.scalar_one_or_none()

        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

        old_status = conv.status
        conv.status = status
        conv.updated_at = datetime.utcnow()

        if status == "ended":
            conv.resolved_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(conv)

        # Audit log
        await self.audit_service.log_action(
            operator_id=operator_id,
            action_type="update_conversation_status",
            target_type="conversation",
            target_id=conversation_id,
            action_details={
                "old_status": old_status,
                "new_status": status,
                "user_id": conv.user_id
            }
        )

        return conv

    async def send_message(
        self,
        conversation_id: str,
        message_request: SendMessageRequest,
        operator_id: str
    ) -> bool:
        """Send message to user in conversation."""
        # Get conversation
        query = select(SupportConversation).where(
            SupportConversation.id == conversation_id
        )
        result = await self.db.execute(query)
        conv = result.scalar_one_or_none()

        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

        # Send message via OpenIM
        success = await self.openim_service.send_message(
            from_user_id=operator_id,
            to_user_id=conv.user_id,
            content=message_request.content,
            content_type=message_request.content_type or 101
        )

        if success:
            # Update conversation
            conv.last_message_at = datetime.utcnow()
            conv.last_message_from = "operator"
            conv.last_message_preview = message_request.content[:200]
            conv.updated_at = datetime.utcnow()
            await self.db.commit()

        return success

    async def batch_send_message(
        self,
        batch_request: BatchSendMessageRequest,
        operator_id: str
    ) -> dict:
        """Send same message to multiple conversations."""
        results = {
            "total": len(batch_request.conversation_ids),
            "success": 0,
            "failed": 0,
            "details": []
        }

        for conv_id in batch_request.conversation_ids:
            try:
                success = await self.send_message(
                    conversation_id=conv_id,
                    message_request=SendMessageRequest(
                        content=batch_request.content,
                        content_type=batch_request.content_type
                    ),
                    operator_id=operator_id
                )

                if success:
                    results["success"] += 1
                    results["details"].append({
                        "conversation_id": conv_id,
                        "status": "success"
                    })
                else:
                    results["failed"] += 1
                    results["details"].append({
                        "conversation_id": conv_id,
                        "status": "failed",
                        "error": "Failed to send message"
                    })
            except Exception as e:
                results["failed"] += 1
                results["details"].append({
                    "conversation_id": conv_id,
                    "status": "failed",
                    "error": str(e)
                })

        # Audit log
        await self.audit_service.log_action(
            operator_id=operator_id,
            action_type="batch_send_message",
            target_type="conversation",
            target_id=",".join(batch_request.conversation_ids[:10]),
            action_details={
                "total": results["total"],
                "success": results["success"],
                "failed": results["failed"]
            }
        )

        return results

    # Quick Reply methods
    async def get_quick_replies(
        self,
        operator_id: str,
        include_shared: bool = True
    ) -> List[QuickReplyResponse]:
        """Get quick replies for operator."""
        query = select(QuickReply)

        if include_shared:
            query = query.where(
                or_(
                    QuickReply.operator_id == operator_id,
                    QuickReply.is_shared == True
                )
            )
        else:
            query = query.where(QuickReply.operator_id == operator_id)

        query = query.order_by(desc(QuickReply.usage_count))

        result = await self.db.execute(query)
        replies = result.scalars().all()

        return [QuickReplyResponse.model_validate(reply) for reply in replies]

    async def create_quick_reply(
        self,
        reply_data: QuickReplyCreate,
        operator_id: str
    ) -> QuickReply:
        """Create new quick reply."""
        reply = QuickReply(
            operator_id=operator_id,
            title=reply_data.title,
            content=reply_data.content,
            is_shared=reply_data.is_shared or False,
            usage_count=0
        )

        self.db.add(reply)
        await self.db.commit()
        await self.db.refresh(reply)

        return reply

    async def update_quick_reply(
        self,
        reply_id: int,
        reply_data: QuickReplyUpdate,
        operator_id: str
    ) -> QuickReply:
        """Update quick reply."""
        query = select(QuickReply).where(
            and_(
                QuickReply.id == reply_id,
                QuickReply.operator_id == operator_id
            )
        )
        result = await self.db.execute(query)
        reply = result.scalar_one_or_none()

        if not reply:
            raise HTTPException(status_code=404, detail="Quick reply not found")

        if reply_data.title is not None:
            reply.title = reply_data.title
        if reply_data.content is not None:
            reply.content = reply_data.content
        if reply_data.is_shared is not None:
            reply.is_shared = reply_data.is_shared

        reply.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(reply)

        return reply

    async def delete_quick_reply(
        self,
        reply_id: int,
        operator_id: str
    ) -> None:
        """Delete quick reply."""
        query = select(QuickReply).where(
            and_(
                QuickReply.id == reply_id,
                QuickReply.operator_id == operator_id
            )
        )
        result = await self.db.execute(query)
        reply = result.scalar_one_or_none()

        if not reply:
            raise HTTPException(status_code=404, detail="Quick reply not found")

        await self.db.delete(reply)
        await self.db.commit()

    async def increment_quick_reply_usage(self, reply_id: int) -> None:
        """Increment usage count for quick reply."""
        query = select(QuickReply).where(QuickReply.id == reply_id)
        result = await self.db.execute(query)
        reply = result.scalar_one_or_none()

        if reply:
            reply.usage_count += 1
            await self.db.commit()

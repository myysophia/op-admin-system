"""Meme service - using Kafka for review queue."""
from datetime import datetime
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from app.models.user import Author
from app.models.post import Post
from app.schemas.meme import (
    MemeSearchParams,
    MemeReviewListResponse,
    MemeReviewListItem,
    MemeReviewRequest
)
from app.services.kafka_service import kafka_service
from app.services.notification_service import notification_service
from app.services.audit_service import AuditService
import logging

logger = logging.getLogger(__name__)


class MemeService:
    """Meme service for reviewing memes from Kafka."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.notification_service = notification_service
        self.audit_service = AuditService(db)
        self.kafka_service = kafka_service

    async def get_pending_memes(self, params: MemeSearchParams) -> MemeReviewListResponse:
        """
        Get pending memes from Kafka queue.

        Args:
            params: Search and pagination parameters

        Returns:
            MemeReviewListResponse with paginated results
        """
        # Calculate offset
        offset = (params.page - 1) * params.page_size

        # Get memes from Kafka service
        memes, total = self.kafka_service.get_pending_memes(
            offset=offset,
            limit=params.page_size,
            user_id=params.user_id,
            symbol=params.symbol,
            name=params.name
        )

        # Preload holdview_amount from posts table
        collection_ids = list({m.get('collection_id') for m in memes if m.get('collection_id')})
        holdview_map: dict[str, int] = {}
        if collection_ids:
            stmt = select(Post.id, Post.holdview_amount).where(Post.id.in_(collection_ids))
            result = await self.db.execute(stmt)
            holdview_map = {row[0]: row[1] for row in result.all()}

        # Enrich with author information if available
        items = []
        for meme in memes:
            # Try to get author info from database
            creator_username = None
            creator_name = None

            if meme.get('user_id'):
                author_query = select(Author).where(Author.user_id == meme['user_id'])
                result = await self.db.execute(author_query)
                author = result.scalar_one_or_none()

                if author:
                    creator_username = author.username
                    creator_name = author.name

            # Build response item
            collection_id = meme.get('collection_id')
            holdview_amount = holdview_map.get(collection_id) if collection_id else None
            if holdview_amount is None and meme.get('holdview_amount') is not None:
                try:
                    holdview_amount = int(meme['holdview_amount'])
                except (TypeError, ValueError):
                    holdview_amount = None

            item = MemeReviewListItem(
                order_id=meme['order_id'],
                user_id=meme['user_id'],
                collection_id=meme['collection_id'],
                name=meme['name'],
                symbol=meme['symbol'],
                avatar=meme['avatar'],
                about=meme['about'],
                chain_id=meme['chain_id'],
                social_links=meme.get('social_links', {}),
                user_region=meme['user_region'],
                holdview_amount=holdview_amount,
                kafka_timestamp=datetime.fromtimestamp(meme['_kafka_timestamp'] / 1000) if meme.get('_kafka_timestamp') else None,
                creator_username=creator_username,
                creator_name=creator_name
            )
            items.append(item)

        return MemeReviewListResponse(
            items=items,
            total=total,
            page=params.page,
            page_size=params.page_size
        )

    async def get_meme_detail(self, order_id: str) -> dict:
        """
        Get meme detail by order_id.

        Args:
            order_id: The unique order ID of the meme

        Returns:
            Meme data dictionary

        Raises:
            HTTPException: If meme not found
        """
        meme = self.kafka_service.get_meme_by_order_id(order_id)

        if not meme:
            raise HTTPException(status_code=404, detail="Meme not found in review queue")

        # Enrich with author info
        if meme.get('user_id'):
            author_query = select(Author).where(Author.user_id == meme['user_id'])
            result = await self.db.execute(author_query)
            author = result.scalar_one_or_none()

            if author:
                meme['creator_username'] = author.username
                meme['creator_name'] = author.name
                meme['creator_avatar'] = author.avatar

        return meme

    async def review_meme(
        self,
        order_id: str,
        review_data: MemeReviewRequest,
        operator_id: str
    ) -> None:
        """
        Review meme (approve or reject).

        - Approve: Send message to approved topic and remove from queue
        - Reject: Simply remove from queue (discard)

        Args:
            order_id: The unique order ID of the meme
            review_data: Review action and optional comment
            operator_id: ID of the operator performing the review

        Raises:
            HTTPException: If meme not found or Kafka error
        """
        # Get meme from queue
        meme = self.kafka_service.get_meme_by_order_id(order_id)

        if not meme:
            raise HTTPException(status_code=404, detail="Meme not found in review queue")

        try:
            if review_data.action == "approve":
                # Send to approved topic
                await self.kafka_service.produce_approved_meme(meme)

                # Notify creator via external notification API
                if meme.get('user_id'):
                    try:
                        await self.notification_service.send_meme_approved_notification(
                            user_id=meme['user_id'],
                            meme_name=meme['name'],
                            meme_symbol=meme['symbol'],
                            order_id=order_id,
                            comment=review_data.comment
                        )
                    except Exception as e:
                        logger.warning(f"Failed to send approval notification: {e}")

                logger.info(f"Meme approved and sent to approved topic: order_id={order_id}")

            else:
                # Reject: just discard
                logger.info(f"Meme rejected and discarded: order_id={order_id}")

                # Notify creator of rejection via external notification API
                if meme.get('user_id'):
                    try:
                        await self.notification_service.send_meme_rejected_notification(
                            user_id=meme['user_id'],
                            meme_name=meme['name'],
                            meme_symbol=meme['symbol'],
                            order_id=order_id,
                            reason=review_data.comment
                        )
                    except Exception as e:
                        logger.warning(f"Failed to send rejection notification: {e}")

            # Remove from pending queue
            removed = self.kafka_service.remove_meme_by_order_id(order_id)

            if not removed:
                logger.warning(f"Meme not found in queue during removal: order_id={order_id}")

            # Audit log
            await self.audit_service.log_action(
                operator_id=operator_id,
                action_type=f"{review_data.action}_meme",
                target_type="meme",
                target_id=order_id,
                action_details={
                    "action": review_data.action,
                    "comment": review_data.comment,
                    "meme_name": meme.get('name'),
                    "meme_symbol": meme.get('symbol'),
                    "user_id": meme.get('user_id'),
                    "collection_id": meme.get('collection_id')
                }
            )

        except Exception as e:
            logger.error(f"Error during meme review: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to process review: {str(e)}")

"""Meme service - now reading pending items from database tables."""
from datetime import datetime
import json
from sqlalchemy import func, select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from app.models.user import Author
from app.models.post import Post, Pair, Collection, PostStatus
from app.schemas.meme import (
    MemeSearchParams,
    MemeReviewListResponse,
    MemeReviewListItem,
    MemeReviewRequest,
)
from app.services.notification_service import notification_service
from app.services.audit_service import AuditService
import logging

logger = logging.getLogger(__name__)

# Pair.status 语义：0 待审核/隐藏，1 审核通过可展示，其余值视为已处理（例如-1表示拒绝）
PENDING_PAIR_STATUS = 0
APPROVED_PAIR_STATUS = 1
REJECTED_PAIR_STATUS = -1


class MemeService:
    """Meme审核服务：从posts/pair表获取待审核记录。"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.notification_service = notification_service
        self.audit_service = AuditService(db)

    async def _get_authors_by_user_ids(self, user_ids: set[str]) -> dict[str, Author]:
        """批量拉取作者信息，减少重复查询。"""
        if not user_ids:
            return {}
        stmt = select(Author).where(Author.user_id.in_(user_ids))
        result = await self.db.execute(stmt)
        return {author.user_id: author for author in result.scalars().all()}

    def _build_filters(self, params: MemeSearchParams):
        filters = [Pair.status == PENDING_PAIR_STATUS]
        if params.user_id:
            filters.append(Pair.creator_id == params.user_id)
        if params.symbol:
            filters.append(Pair.base_symbol.ilike(f"%{params.symbol}%"))
        if params.name:
            filters.append(Pair.base_name.ilike(f"%{params.name}%"))
        return filters

    async def get_pending_memes(self, params: MemeSearchParams) -> MemeReviewListResponse:
        """
        获取待审核的meme，数据来源posts/pair。
        """
        offset = (params.page - 1) * params.page_size
        filters = self._build_filters(params)

        base_query = (
            select(Pair, Post, Collection, Author)
            .join(Post, Pair.collection_id == Post.id, isouter=True)
            .join(Collection, Collection.id == Post.id, isouter=True)
            .join(
                Author,
                (Author.user_id == Pair.creator_id) | (Author.id == Pair.creator_id),
                isouter=True,
            )
            .where(*filters)
        )

        if params.creator_name:
            name_pattern = f"%{params.creator_name}%"
            base_query = base_query.where(Author.name.ilike(name_pattern))

        count_stmt = select(func.count()).select_from(base_query.subquery())
        total = await self.db.scalar(count_stmt) or 0

        data_stmt = (
            base_query
            .order_by(Pair.created_at.desc().nulls_last(), Pair.id.desc())
            .offset(offset)
            .limit(params.page_size)
        )
        result = await self.db.execute(data_stmt)
        rows = result.all()

        items = []
        for pair, post, collection, creator in rows:
            created_at = pair.created_at or pair.base_created_at or (post.created_at if post else None)
            avatar = pair.base_image_url or (collection.cover if collection else None) or ""
            social_links = self._normalize_social_links(pair.social_links)
            item = MemeReviewListItem(
                order_id=str(pair.id),
                user_id=pair.creator_id or "",
                collection_id=pair.collection_id or (post.id if post else ""),
                name=pair.base_name or "",
                symbol=pair.base_symbol or "",
                avatar=avatar,
                about=pair.base_description or "",
                chain_id=pair.chain,
                social_links=social_links,
                user_region=post.region if post and post.region else "US",
                holdview_amount=post.holdview_amount if post else None,
                kafka_timestamp=created_at,
                creator_username=creator.username if creator else None,
                creator_name=creator.name if creator else None,
            )
            items.append(item)

        return MemeReviewListResponse(
            items=items,
            total=total,
            page=params.page,
            page_size=params.page_size,
        )

    async def get_meme_detail(self, order_id: str) -> dict:
        """
        根据pair.id（兼容旧order_id概念）读取详情。
        """
        try:
            pair_id = int(order_id)
        except (TypeError, ValueError):
            raise HTTPException(status_code=404, detail="Meme not found in review queue")

        stmt = (
            select(Pair, Post, Collection)
            .join(Post, Pair.collection_id == Post.id, isouter=True)
            .join(Collection, Collection.id == Post.id, isouter=True)
            .where(Pair.id == pair_id)
        )
        result = await self.db.execute(stmt)
        row = result.first()

        if not row:
            raise HTTPException(status_code=404, detail="Meme not found in review queue")

        pair, post, collection = row
        author_map = await self._get_authors_by_user_ids({pair.creator_id} if pair.creator_id else set())
        creator = author_map.get(pair.creator_id) if pair else None

        created_at = pair.created_at or pair.base_created_at or (post.created_at if post else None)
        avatar = pair.base_image_url or (collection.cover if collection else None) or ""
        social_links = self._normalize_social_links(pair.social_links)

        return {
            "order_id": str(pair.id),
            "user_id": pair.creator_id,
            "collection_id": pair.collection_id or (post.id if post else None),
            "name": pair.base_name,
            "symbol": pair.base_symbol,
            "avatar": avatar,
            "about": pair.base_description,
            "chain_id": pair.chain,
            "social_links": social_links,
            "user_region": post.region if post and post.region else "US",
            "holdview_amount": post.holdview_amount if post else None,
            "created_at": created_at,
            "pair_status": pair.status,
            "post_status": post.status if post else None,
            "collection_cover": collection.cover if collection else None,
            "collection_description": collection.description if collection else None,
            "creator_username": creator.username if creator else None,
            "creator_name": creator.name if creator else None,
        }

    def _normalize_social_links(self, value):
        """社交链接字段兼容字符串/None，返回dict。"""
        if not value:
            return {}
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                logger.warning("social_links 解析失败，返回空字典", extra={"value": value})
                return {}
        return {}

    async def review_meme(
        self,
        order_id: str,
        review_data: MemeReviewRequest,
        operator_id: str,
    ) -> None:
        """
        审核meme：基于pair状态更新，移除待审核列表并通知创作者。
        """
        try:
            pair_id = int(order_id)
        except (TypeError, ValueError):
            raise HTTPException(status_code=404, detail="Meme not found in review queue")

        stmt = (
            select(Pair, Post)
            .join(Post, Pair.collection_id == Post.id, isouter=True)
            .where(Pair.id == pair_id)
        )
        result = await self.db.execute(stmt)
        row = result.first()

        if not row:
            raise HTTPException(status_code=404, detail="Meme not found in review queue")

        pair, post = row
        if pair.status != PENDING_PAIR_STATUS:
            raise HTTPException(status_code=400, detail="Meme already reviewed or unavailable")

        # 预先缓存通知与审计所需字段，避免删除后取值失败
        meme_meta = {
            "pair_id": pair.id,
            "creator_id": pair.creator_id,
            "collection_id": pair.collection_id,
            "base_name": pair.base_name,
            "base_symbol": pair.base_symbol,
        }

        try:
            now = datetime.utcnow()
            if review_data.action == "approve":
                pair.status = APPROVED_PAIR_STATUS
                if post:
                    post.status = PostStatus.POSTED.value
                    post.updated_at = now
            else:
                pair.status = REJECTED_PAIR_STATUS
                if post:
                    post.status = PostStatus.DELETED.value
                    post.updated_at = now
                if pair.collection_id:
                    await self.db.execute(delete(Pair).where(Pair.collection_id == pair.collection_id))
                    await self.db.execute(delete(Collection).where(Collection.id == pair.collection_id))

            await self.db.commit()

        except HTTPException:
            await self.db.rollback()
            raise
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error during meme review: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to process review: {str(e)}")

        # 审核结果通知（失败不影响主流程）
        if meme_meta["creator_id"]:
            try:
                if review_data.action == "approve":
                    await self.notification_service.send_meme_approved_notification(
                        user_id=meme_meta["creator_id"],
                        meme_name=meme_meta["base_name"],
                        meme_symbol=meme_meta["base_symbol"],
                        order_id=str(meme_meta["pair_id"]),
                        comment=review_data.comment,
                    )
                else:
                    await self.notification_service.send_meme_rejected_notification(
                        user_id=meme_meta["creator_id"],
                        meme_name=meme_meta["base_name"],
                        meme_symbol=meme_meta["base_symbol"],
                        order_id=str(meme_meta["pair_id"]),
                        reason=review_data.comment,
                    )
            except Exception as e:
                logger.warning(f"Failed to send meme review notification: {e}")

        # 审计记录
        await self.audit_service.log_action(
            operator_id=operator_id,
            action_type=f"{review_data.action}_meme",
            target_type="meme",
            target_id=str(meme_meta["pair_id"]),
            action_details={
                "action": review_data.action,
                "comment": review_data.comment,
                "meme_name": meme_meta["base_name"],
                "meme_symbol": meme_meta["base_symbol"],
                "user_id": meme_meta["creator_id"],
                "collection_id": meme_meta["collection_id"],
            },
        )

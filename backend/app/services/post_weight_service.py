"""Post weight service."""
from datetime import datetime
from typing import Dict, Iterable, List, Tuple
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.post import Post
from app.models.post_weight import PostWeight
from app.schemas.post_weight import (
    PostWeightCreateRequest,
    PostWeightListResponse,
    PostWeightResponse,
)


class PostWeightService:
    """Service for managing post weights."""

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _extract_post_id(post_url: str) -> str:
        parsed = urlparse(post_url)
        path = parsed.path or ""
        segments = [segment for segment in path.split("/") if segment]
        if not segments:
            raise ValueError("URL路径中未找到post_id")
        return segments[-1]

    @staticmethod
    def _normalize_urls(post_urls: str) -> List[Tuple[str, str]]:
        normalized: List[Tuple[str, str]] = []
        seen_ids: set[str] = set()

        for raw in post_urls.split(","):
            url = raw.strip()
            if not url:
                continue
            try:
                post_id = PostWeightService._extract_post_id(url)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=f"无法从URL解析post_id: {url}") from exc
            if post_id not in seen_ids:
                normalized.append((url, post_id))
                seen_ids.add(post_id)

        return normalized

    async def create_or_update(
        self,
        payload: PostWeightCreateRequest,
        operator_id: str,
        operator_name: str,
    ) -> List[PostWeightResponse]:
        """Create or update post weights."""
        pairs = self._normalize_urls(payload.post_urls)
        if not pairs:
            raise HTTPException(status_code=400, detail="post_urls不能为空")

        post_ids = [post_id for _, post_id in pairs]

        # Validate post existence
        query = select(Post.id).where(Post.id.in_(post_ids))
        result = await self.db.execute(query)
        existing_ids = set(result.scalars().all())
        missing_ids = [pid for pid in post_ids if pid not in existing_ids]
        if missing_ids:
            raise HTTPException(
                status_code=404,
                detail=f"以下post_id不存在: {', '.join(missing_ids)}"
            )

        # Fetch existing weights
        weight_stmt = select(PostWeight).where(PostWeight.post_id.in_(post_ids))
        weight_result = await self.db.execute(weight_stmt)
        existing_weights: Dict[str, PostWeight] = {
            item.post_id: item for item in weight_result.scalars().all()
        }

        now = datetime.utcnow()
        operator = operator_id
        operator_display_name = payload.operator or operator_name or operator_id

        affected_records: List[PostWeight] = []

        # Upsert logic
        for post_url, post_id in pairs:
            record = existing_weights.get(post_id)
            if record is None:
                record = PostWeight(
                    post_url=post_url,
                    post_id=post_id,
                    weight=payload.weight,
                    operator=operator,
                    operator_name=operator_display_name,
                    created_at=now,
                    updated_at=now,
                )
                self.db.add(record)
            else:
                record.post_url = post_url
                record.weight = payload.weight
                record.operator = operator
                record.operator_name = operator_display_name
                record.deleted_at = None
                record.updated_at = now

            affected_records.append(record)

        await self.db.flush()

        # Notify recommendation service before committing
        await self._notify_recommendation(post_ids)

        await self.db.commit()

        # Refresh records to return latest values
        for record in affected_records:
            await self.db.refresh(record)

        return [PostWeightResponse.model_validate(record) for record in affected_records]

    async def list_post_weights(
        self,
        page: int,
        page_size: int,
    ) -> PostWeightListResponse:
        """List post weight records."""
        if page < 1 or page_size < 1:
            raise HTTPException(status_code=400, detail="分页参数不合法")

        base_condition = PostWeight.deleted_at.is_(None)

        count_stmt = select(func.count()).select_from(PostWeight).where(base_condition)
        total = await self.db.scalar(count_stmt) or 0

        stmt = (
            select(PostWeight)
            .where(base_condition)
            .order_by(PostWeight.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.db.execute(stmt)
        items = [PostWeightResponse.model_validate(record) for record in result.scalars().all()]

        return PostWeightListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )

    async def soft_delete(self, record_id: int) -> None:
        """Soft delete a post weight record."""
        stmt = select(PostWeight).where(
            PostWeight.id == record_id,
            PostWeight.deleted_at.is_(None),
        )
        result = await self.db.execute(stmt)
        record = result.scalar_one_or_none()

        if not record:
            raise HTTPException(status_code=404, detail="记录不存在或已删除")

        record.deleted_at = datetime.utcnow()
        record.updated_at = datetime.utcnow()
        await self.db.flush()

        await self._notify_remove([record.post_id])

        await self.db.commit()

    async def cancel_weights(self, post_ids: List[str]) -> Dict[str, int]:
        """批量取消帖子权重并同步推荐系统。"""
        normalized_ids = [pid.strip() for pid in post_ids if pid and pid.strip()]
        normalized_ids = list(dict.fromkeys(normalized_ids))

        if not normalized_ids:
            raise HTTPException(status_code=400, detail="post_ids不能为空")

        stmt = select(PostWeight).where(
            PostWeight.post_id.in_(normalized_ids),
            PostWeight.deleted_at.is_(None),
        )
        result = await self.db.execute(stmt)
        records = result.scalars().all()

        now = datetime.utcnow()
        updated = 0
        for record in records:
            record.deleted_at = now
            record.updated_at = now
            updated += 1

        await self.db.flush()

        await self._notify_remove(normalized_ids)

        await self.db.commit()

        return {"requested": len(normalized_ids), "updated": updated}

    async def _notify_recommendation(self, post_ids: Iterable[str]) -> None:
        """Call external recommendation service."""
        if not settings.POST_WEIGHT_API_URL:
            return

        post_ids = list(post_ids)
        if not post_ids:
            return

        headers = {"Content-Type": "application/json"}
        if settings.POST_WEIGHT_API_TOKEN:
            headers["X-Token"] = settings.POST_WEIGHT_API_TOKEN

        payload = {"post_ids": post_ids}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    settings.POST_WEIGHT_API_URL,
                    json=payload,
                    headers=headers,
                )

            if response.status_code != 200:
                await self.db.rollback()
                raise HTTPException(
                    status_code=502,
                    detail=(
                        f"推荐系统返回异常状态: {response.status_code}, body={response.text}, payload={payload}"
                    ),
                )

        except HTTPException:
            raise
        except Exception as exc:
            await self.db.rollback()
            raise HTTPException(
                status_code=502,
                detail=f"推荐系统调用失败: {exc}, payload={payload}"
            ) from exc

    async def _notify_remove(self, post_ids: Iterable[str]) -> None:
        """通知推荐系统移除帖子权重。"""
        if not settings.POST_WEIGHT_REMOVE_API_URL:
            return

        post_ids = list(post_ids)
        if not post_ids:
            return

        headers = {"Content-Type": "application/json"}
        if settings.POST_WEIGHT_API_TOKEN:
            headers["X-Token"] = settings.POST_WEIGHT_API_TOKEN

        payload = {"post_ids": post_ids}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    settings.POST_WEIGHT_REMOVE_API_URL,
                    json=payload,
                    headers=headers,
                )

            if response.status_code != 200:
                await self.db.rollback()
                raise HTTPException(
                    status_code=502,
                    detail=(
                        f"推荐系统删除接口返回异常: {response.status_code}, body={response.text}, payload={payload}"
                    ),
                )

        except HTTPException:
            raise
        except Exception as exc:
            await self.db.rollback()
            raise HTTPException(
                status_code=502,
                detail=f"推荐系统删除调用失败: {exc}, payload={payload}"
            ) from exc

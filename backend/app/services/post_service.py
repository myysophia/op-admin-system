"""Post service layer."""
from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from app.models.meme import Post, PostWeightRecord
from app.schemas.meme import (
    PostSearchParams,
    PostListResponse,
    PostResponse,
    PostCreate,
    PostWeightUpdateRequest
)
from app.services.audit_service import AuditService
import re


class PostService:
    """Post service."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.audit_service = AuditService(db)

    def validate_post_url(self, url: str) -> bool:
        """
        Validate post URL format.
        TODO: Implement specific URL validation rules based on requirements
        """
        # Basic URL validation
        url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain
            r'localhost|'  # localhost
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # or IP
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)

        return bool(url_pattern.match(url))

    async def get_posts(self, params: PostSearchParams) -> PostListResponse:
        """Get post list with search and pagination."""
        # Build query
        query = select(Post).where(Post.status == "active")

        # Apply filters
        if params.meme_id:
            query = query.where(Post.meme_id == params.meme_id)

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total = await self.db.scalar(count_query)

        # Apply sorting
        if params.sort_by == "weight":
            query = query.order_by(Post.weight.desc())
        else:
            query = query.order_by(Post.created_at.desc())

        # Apply pagination
        offset = (params.page - 1) * params.page_size
        query = query.offset(offset).limit(params.page_size)

        # Execute query
        result = await self.db.execute(query)
        posts = result.scalars().all()

        return PostListResponse(
            items=[PostResponse.model_validate(post) for post in posts],
            total=total or 0,
            page=params.page,
            page_size=params.page_size
        )

    async def create_post(
        self,
        post_data: PostCreate,
        operator_id: int
    ) -> PostResponse:
        """Create new post."""
        # Validate URL
        if not self.validate_post_url(post_data.post_url):
            raise HTTPException(status_code=400, detail="Invalid post URL format")

        # Check if URL already exists
        query = select(Post).where(Post.post_url == post_data.post_url)
        result = await self.db.execute(query)
        existing_post = result.scalar_one_or_none()

        if existing_post:
            raise HTTPException(status_code=400, detail="Post URL already exists")

        # Create post
        post = Post(
            post_url=post_data.post_url,
            meme_id=post_data.meme_id,
            content=post_data.content,
            weight=post_data.weight,
            creator_uid=operator_id,
            status="active"
        )

        self.db.add(post)
        await self.db.commit()
        await self.db.refresh(post)

        # Audit log
        await self.audit_service.log_action(
            operator_id=str(operator_id),
            action_type="create_post",
            target_type="post",
            target_id=str(post.id),
            action_details=post_data.model_dump()
        )

        return PostResponse.model_validate(post)

    async def update_weight(
        self,
        post_id: int,
        weight_data: PostWeightUpdateRequest,
        operator_id: int
    ) -> None:
        """Update post weight."""
        # Get post
        query = select(Post).where(Post.id == post_id)
        result = await self.db.execute(query)
        post = result.scalar_one_or_none()

        if not post:
            raise HTTPException(status_code=404, detail="Post not found")

        # Create weight adjustment record
        weight_record = PostWeightRecord(
            post_id=post_id,
            operator_id=operator_id,
            old_weight=post.weight,
            new_weight=weight_data.weight,
            reason=weight_data.reason
        )
        self.db.add(weight_record)

        # Update post weight
        post.weight = weight_data.weight
        post.updated_at = datetime.utcnow()

        await self.db.commit()

        # Audit log
        await self.audit_service.log_action(
            operator_id=str(operator_id),
            action_type="update_post_weight",
            target_type="post",
            target_id=str(post_id),
            action_details=weight_data.model_dump()
        )

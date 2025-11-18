"""Support service for会话状态管理."""
from __future__ import annotations

from datetime import datetime
import mimetypes
import uuid
import zlib
from pathlib import Path
from typing import Dict, List, Optional, Set

from fastapi import HTTPException
from sqlalchemy import and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.support import SupportConversation, SupportQuickMessage
from app.models.user import Author, User, UserWallet
from app.schemas.support import (
    SupportConversationCreateRequest,
    SupportConversationCreateResponse,
    SupportConversationDetailResponse,
    SupportConversationListItem,
    SupportConversationListResponse,
    SupportConversationMessage,
    SupportConversationQuery,
    SupportConversationStatusUpdateRequest,
    SupportConversationUserProfile,
    SupportImLookupItem,
    SupportImLookupResponse,
    SupportQuickMessageCreateRequest,
    SupportQuickMessageItem,
    SupportQuickMessageListResponse,
    SupportQuickMessageUpdateRequest,
    SupportQuickMessageUploadResponse,
)
from app.services.audit_service import AuditService
from app.utils.r2_storage import R2Config, R2StorageClient, R2StorageError


async def _resolve_operator_display_name(
    db: AsyncSession,
    operator_id: str,
    fallback: Optional[str] = None,
) -> str:
    """从authors表反查运营用户名，失败时回退。"""

    if not operator_id:
        return fallback or ""

    stmt = select(Author.username).where(Author.id == operator_id)
    username = await db.scalar(stmt)
    if username:
        return username

    return fallback or operator_id


class SupportService:
    """客服会话状态管理."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.audit_service = AuditService(db)
        self.uid_salt = settings.AGORA_UID_SALT or "JyzuC2!EPq8@EvF-zdqjdsh6NTpkr_nz"
        self.MAX_UID = 2_147_483_647

    # ------------------------------------------------------------------ #
    async def create_or_update_conversation(
        self,
        payload: SupportConversationCreateRequest,
    ) -> SupportConversationCreateResponse:
        """创建或刷新会话，状态重置为pending。"""
        existing = await self._get_conversation_by_openim(payload.openim_conversation_id)
        # 校验用户存在
        await self._build_user_profile(payload.user_id)
        messages = self._merge_messages(existing.messages if existing else None, payload.messages)

        if existing:
            existing.user_id = payload.user_id
            existing.status = "pending"
            existing.last_message = payload.last_message
            existing.last_message_at = payload.last_message_at
            existing.messages = messages
            existing.task_id = payload.task_id
            existing.device_type = payload.device_type
            existing.device_id = payload.device_id
            existing.app_version = payload.app_version
            existing.resolved_at = None
            existing.operator_id = None
            existing.operator_name = None
        else:
            existing = SupportConversation(
                id=str(uuid.uuid4()),
                user_id=payload.user_id,
                openim_conversation_id=payload.openim_conversation_id,
                status="pending",
                last_message=payload.last_message,
                last_message_at=payload.last_message_at,
                messages=messages,
                task_id=payload.task_id,
                device_type=payload.device_type,
                device_id=payload.device_id,
                app_version=payload.app_version,
            )
            self.db.add(existing)

        await self.db.commit()
        return SupportConversationCreateResponse(
            conversation_id=existing.id,
            status=existing.status,
        )

    # ------------------------------------------------------------------ #
    async def list_conversations(
        self,
        query: SupportConversationQuery,
    ) -> SupportConversationListResponse:
        """分页查询会话列表。"""
        stmt = select(SupportConversation)

        filters = []
        if query.status:
            filters.append(SupportConversation.status == query.status)
        if query.uid:
            filters.append(SupportConversation.user_id.ilike(f"%{query.uid}%"))
        if query.username:
            author_subq = (
                select(Author.user_id)
                .where(Author.username.ilike(f"%{query.username}%"))
            )
            filters.append(SupportConversation.user_id.in_(author_subq))

        if query.display_name:
            display_subq = (
                select(Author.user_id)
                .where(Author.name.ilike(f"%{query.display_name}%"))
            )
            filters.append(SupportConversation.user_id.in_(display_subq))

        if query.wallet_address:
            wallet_subq = (
                select(UserWallet.user_id)
                .where(UserWallet.pubkey.ilike(f"%{query.wallet_address}%"))
            )
            filters.append(SupportConversation.user_id.in_(wallet_subq))

        if filters:
            stmt = stmt.where(and_(*filters))

        stmt = stmt.order_by(
            SupportConversation.last_message_at.desc().nullslast(),
            SupportConversation.created_at.desc(),
        )

        total_query = select(func.count()).select_from(stmt.subquery())
        total = await self.db.scalar(total_query) or 0

        offset = (query.page - 1) * query.page_size
        stmt = stmt.offset(offset).limit(query.page_size)

        result = await self.db.execute(stmt)
        conversations = result.scalars().all()

        profiles = await self._build_bulk_profiles({conv.user_id for conv in conversations})

        items = []
        for conv in conversations:
            profile = profiles.get(conv.user_id)
            items.append(
                SupportConversationListItem(
                    conversation_id=conv.id,
                    openim_conversation_id=conv.openim_conversation_id,
                    user_id=conv.user_id,
                    username=profile.username if profile else None,
                    display_name=profile.display_name if profile else None,
                    wallet_address=profile.wallet_address if profile else None,
                    status=conv.status,
                    last_message=conv.last_message,
                    last_message_at=conv.last_message_at,
                    app_version=conv.app_version,
                )
            )

        return SupportConversationListResponse(
            items=items,
            total=total,
            page=query.page,
            page_size=query.page_size,
        )

    # ------------------------------------------------------------------ #
    async def get_conversation_detail(self, conversation_id: str) -> SupportConversationDetailResponse:
        stmt = select(SupportConversation).where(SupportConversation.id == conversation_id)
        result = await self.db.execute(stmt)
        conversation = result.scalar_one_or_none()
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        base_profile = await self._build_user_profile(conversation.user_id)
        base_data = (
            base_profile.model_dump()  # Pydantic v2
            if hasattr(base_profile, "model_dump")
            else base_profile.dict()
        )
        base_data.update(
            {
                "task_id": conversation.task_id or base_data.get("task_id"),
                "device_type": conversation.device_type or base_data.get("device_type"),
                "device_id": conversation.device_id or base_data.get("device_id"),
                "app_version": conversation.app_version or base_data.get("app_version"),
            }
        )
        merged_profile = SupportConversationUserProfile(**base_data)

        messages = [
            SupportConversationMessage(**message)
            for message in (conversation.messages or [])
        ]

        return SupportConversationDetailResponse(
            conversation_id=conversation.id,
            openim_conversation_id=conversation.openim_conversation_id,
            status=conversation.status,
            last_message=conversation.last_message,
            last_message_at=conversation.last_message_at,
            messages=messages,
            user_profile=merged_profile,
        )

    # ------------------------------------------------------------------ #
    async def update_status(
        self,
        conversation_id: str,
        payload: SupportConversationStatusUpdateRequest,
        operator_id: str,
        operator_name: str,
    ) -> None:
        stmt = select(SupportConversation).where(SupportConversation.id == conversation_id)
        result = await self.db.execute(stmt)
        conversation = result.scalar_one_or_none()

        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        conversation.status = payload.status
        conversation.operator_id = operator_id
        resolved_operator_name = await _resolve_operator_display_name(self.db, operator_id, operator_name)
        conversation.operator_name = resolved_operator_name
        conversation.resolved_at = datetime.utcnow() if payload.status in {"processed", "later"} else None
        conversation.updated_at = datetime.utcnow()

        await self.db.commit()

        await self.audit_service.log_action(
            operator_id=operator_id,
            action_type="support_conversation_status_update",
            target_type="support_conversation",
            target_id=conversation.id,
            action_details={
                "status": payload.status,
                "operator_name": resolved_operator_name,
            },
            )

    # ------------------------------------------------------------------ #
    async def lookup_users_by_im_ids(self, im_ids: List[str]) -> SupportImLookupResponse:
        """根据IM ID批量返回用户信息."""
        normalized = []
        seen = set()
        for im_id in im_ids:
            if not im_id:
                continue
            value = im_id.strip()
            if not value or value in seen:
                continue
            seen.add(value)
            normalized.append(value)

        if not normalized:
            return SupportImLookupResponse(items=[])

        query = text("SELECT im_id, toci_id FROM toci_im WHERE im_id = ANY(:im_ids)")
        rows = await self.db.execute(query, {"im_ids": normalized})
        im_map = {row[0]: row[1] for row in rows}

        profiles = await self._build_bulk_profiles(set(im_map.values()))

        items = []
        for im_id in normalized:
            user_id = im_map.get(im_id)
            profile = profiles.get(user_id) if user_id else None
            items.append(
                SupportImLookupItem(
                    im_id=im_id,
                    found=profile is not None,
                    user_profile=profile,
                )
            )

        return SupportImLookupResponse(items=items)

    # ------------------------------------------------------------------ #
    async def _get_conversation_by_openim(self, openim_id: str) -> SupportConversation | None:
        stmt = select(SupportConversation).where(SupportConversation.openim_conversation_id == openim_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    def _merge_messages(
        self,
        existing: List[dict] | None,
        incoming: List[SupportConversationMessage],
        limit: int = 20,
    ) -> List[dict]:
        history = list(existing or [])
        if incoming:
            for message in incoming:
                data = (
                    message.model_dump(exclude_none=True)
                    if hasattr(message, "model_dump")
                    else message.dict(exclude_none=True)
                )
                history.append(data)
        return history[-limit:]

    async def _build_user_profile(self, user_id: str) -> SupportConversationUserProfile:
        profiles = await self._build_bulk_profiles({user_id})
        profile = profiles.get(user_id)
        if not profile:
            raise HTTPException(status_code=404, detail="User not found for conversation")
        return profile

    async def _build_bulk_profiles(self, user_ids: Set[str]) -> Dict[str, SupportConversationUserProfile]:
        if not user_ids:
            return {}

        stmt = (
            select(User, Author)
            .outerjoin(Author, Author.user_id == User.id)
            .where(User.id.in_(user_ids))
        )
        result = await self.db.execute(stmt)
        rows = result.all()
        if not rows:
            return {}

        user_map: Dict[str, tuple[User, Author | None]] = {}
        for user, author in rows:
            user_map[user.id] = (user, author)

        wallet_stmt = (
            select(UserWallet.user_id, UserWallet.pubkey, UserWallet.created_at)
            .where(UserWallet.user_id.in_(user_ids))
            .order_by(UserWallet.user_id, UserWallet.created_at.desc().nullslast())
        )
        wallet_result = await self.db.execute(wallet_stmt)
        wallet_map: Dict[str, str] = {}
        for user_id, pubkey, _created_at in wallet_result:
            if user_id not in wallet_map:
                wallet_map[user_id] = pubkey

        im_rows = await self.db.execute(
            text("SELECT toci_id, im_id FROM toci_im WHERE toci_id = ANY(:ids)"),
            {"ids": list(user_ids)},
        )
        im_map = {row[0]: row[1] for row in im_rows}

        profiles: Dict[str, SupportConversationUserProfile] = {}
        for user_id, (user, author) in user_map.items():
            profiles[user_id] = SupportConversationUserProfile(
                user_id=user.id,
                username=author.username if author else None,
                display_name=author.name if author else None,
                wallet_address=wallet_map.get(user_id),
                agora_uid=self._generate_agora_uid(user.id),
                im_id=im_map.get(user_id),
                task_id=None,
                device_type=None,
                device_id=None,
                app_version=None,
                registered_email=author.email if author and author.email else user.email,
                tel=author.phone_number if author and author.phone_number else user.phone_number,
            )

        return profiles

    def _generate_agora_uid(self, user_id: str) -> int:
        salted_input = f"{self.uid_salt}:{user_id}"
        crc32_hash = zlib.crc32(salted_input.encode("utf-8")) & 0xFFFFFFFF
        return (crc32_hash % (self.MAX_UID - 1)) + 1


class SupportQuickMessageService:
    """客服快捷消息管理服务。"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.audit_service = AuditService(db)
        self._r2_client: Optional[R2StorageClient] = None

    # ----------------------------- CRUD ----------------------------- #
    async def list_quick_messages(self, active_only: bool) -> SupportQuickMessageListResponse:
        stmt = select(SupportQuickMessage)
        if active_only:
            stmt = stmt.where(SupportQuickMessage.is_active.is_(True))

        stmt = stmt.order_by(
            SupportQuickMessage.sort_order.asc(),
            SupportQuickMessage.created_at.desc(),
        )

        result = await self.db.execute(stmt)
        items = [SupportQuickMessageItem.model_validate(row) for row in result.scalars().all()]
        return SupportQuickMessageListResponse(items=items)

    async def create_quick_message(
        self,
        payload: SupportQuickMessageCreateRequest,
        operator_id: str,
    ) -> SupportQuickMessageItem:
        resolved_name = await _resolve_operator_display_name(self.db, operator_id)

        quick_message = SupportQuickMessage(
            title=payload.title,
            content=payload.content,
            image_key=payload.image_key,
            image_url=payload.image_url,
            sort_order=payload.sort_order,
            is_active=payload.is_active,
            created_by=operator_id,
            created_by_name=resolved_name,
            updated_by=operator_id,
            updated_by_name=resolved_name,
        )
        self.db.add(quick_message)
        await self.db.commit()
        await self.db.refresh(quick_message)

        await self.audit_service.log_action(
            operator_id=operator_id,
            action_type="support_quick_message_create",
            target_type="support_quick_message",
            target_id=quick_message.id,
            action_details=payload.model_dump(),
        )

        return SupportQuickMessageItem.model_validate(quick_message)

    async def update_quick_message(
        self,
        message_id: str,
        payload: SupportQuickMessageUpdateRequest,
        operator_id: str,
    ) -> SupportQuickMessageItem:
        quick_message = await self._get_quick_message(message_id)
        updates = payload.model_dump(exclude_unset=True)
        if not updates:
            raise HTTPException(status_code=400, detail="未提供需要更新的字段")

        for field, value in updates.items():
            setattr(quick_message, field, value)

        resolved_name = await _resolve_operator_display_name(self.db, operator_id)
        quick_message.updated_by = operator_id
        quick_message.updated_by_name = resolved_name

        await self.db.commit()
        await self.db.refresh(quick_message)

        await self.audit_service.log_action(
            operator_id=operator_id,
            action_type="support_quick_message_update",
            target_type="support_quick_message",
            target_id=quick_message.id,
            action_details=updates,
        )

        return SupportQuickMessageItem.model_validate(quick_message)

    async def delete_quick_message(self, message_id: str, operator_id: str) -> None:
        quick_message = await self._get_quick_message(message_id)
        title_snapshot = quick_message.title
        await self.db.delete(quick_message)
        await self.db.commit()

        await self.audit_service.log_action(
            operator_id=operator_id,
            action_type="support_quick_message_delete",
            target_type="support_quick_message",
            target_id=message_id,
            action_details={"title": title_snapshot},
        )

    # ----------------------------- 上传 ----------------------------- #
    async def upload_image(
        self,
        *,
        operator_id: str,
        filename: Optional[str],
        content_type: Optional[str],
        data: bytes,
    ) -> SupportQuickMessageUploadResponse:
        if not data:
            raise HTTPException(status_code=400, detail="上传内容为空")

        max_size = settings.MAX_UPLOAD_SIZE or 10 * 1024 * 1024
        if len(data) > max_size:
            raise HTTPException(status_code=413, detail="图片大小超出限制")

        detected_content_type = content_type or mimetypes.guess_type(filename or "")[0]
        if not detected_content_type:
            detected_content_type = "application/octet-stream"

        if not detected_content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="仅支持图片格式上传")

        suffix = Path(filename).suffix if filename else ""
        if not suffix:
            guessed = mimetypes.guess_extension(detected_content_type)
            suffix = guessed or ""
        if suffix and not suffix.startswith("."):
            suffix = f".{suffix}"

        object_key = f"support/quick-messages/{operator_id}/{uuid.uuid4().hex}{suffix}"

        client = self._get_r2_client()
        try:
            url = await client.upload_bytes(key=object_key, data=data, content_type=detected_content_type)
        except R2StorageError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        return SupportQuickMessageUploadResponse(
            key=object_key,
            url=url,
            content_type=detected_content_type,
            size=len(data),
        )

    # ----------------------------- helpers ----------------------------- #
    async def _get_quick_message(self, message_id: str) -> SupportQuickMessage:
        stmt = select(SupportQuickMessage).where(SupportQuickMessage.id == message_id)
        result = await self.db.execute(stmt)
        quick_message = result.scalar_one_or_none()
        if not quick_message:
            raise HTTPException(status_code=404, detail="快捷消息不存在")
        return quick_message

    def _get_r2_client(self) -> R2StorageClient:
        if self._r2_client:
            return self._r2_client

        required = {
            "CF_R2_ENDPOINT": settings.CF_R2_ENDPOINT,
            "CF_R2_ACCESS_KEY_ID": settings.CF_R2_ACCESS_KEY_ID,
            "CF_R2_SECRET_ACCESS_KEY": settings.CF_R2_SECRET_ACCESS_KEY,
            "CF_R2_BUCKET": settings.CF_R2_BUCKET,
        }
        missing = [key for key, value in required.items() if not value]
        if missing:
            raise HTTPException(status_code=500, detail=f"R2配置缺失: {', '.join(missing)}")

        public_url = settings.CF_R2_IMAGES_MEMEFANS_ACCESS_URL or settings.CF_R2_FILES_MEMEFANS_ACCESS_URL

        config = R2Config(
            endpoint_url=settings.CF_R2_ENDPOINT,
            access_key_id=settings.CF_R2_ACCESS_KEY_ID,
            secret_access_key=settings.CF_R2_SECRET_ACCESS_KEY,
            bucket=settings.CF_R2_BUCKET,
            public_base_url=public_url,
        )
        self._r2_client = R2StorageClient(config)
        return self._r2_client

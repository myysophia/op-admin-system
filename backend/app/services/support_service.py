"""Support service for会话状态管理."""
from __future__ import annotations

from datetime import datetime
import json
import mimetypes
import uuid
import zlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from fastapi import HTTPException
from sqlalchemy import select, text, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.support import SupportQuickMessage, SupportChatStatus, SupportCase
from app.models.user import Author, User, UserWallet
from app.schemas.support import (
    SupportConversationCreateRequest,
    SupportConversationCreateResponse,
    SupportConversationDetailResponse,
    SupportConversationListItem,
    SupportConversationListResponse,
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
    SupportCaseCreateRequest,
    SupportCaseUpdateRequest,
    SupportCaseItem,
    SupportCaseListResponse,
)
from app.services.audit_service import AuditService
from app.services.openim_service import openim_service
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


    # ----------------------------- Support Case CRUD ----------------------------- #
    async def create_case(self, payload: SupportCaseCreateRequest) -> SupportCaseItem:
        case = SupportCase(
            support_id=str(uuid.uuid4()),
            user_id=payload.user_id,
            title=payload.title,
            comment=payload.comment,
            status=payload.status or "open",
        )
        self.db.add(case)
        await self.db.commit()
        await self.db.refresh(case)
        return SupportCaseItem.model_validate(case)

    async def get_case(self, case_id: str) -> SupportCaseItem:
        stmt = select(SupportCase).where(SupportCase.id == case_id)
        result = await self.db.execute(stmt)
        case = result.scalar_one_or_none()
        if not case:
            raise HTTPException(status_code=404, detail="Support case not found")
        return SupportCaseItem.model_validate(case)

    async def list_cases(
        self,
        page: int,
        page_size: int,
        status: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> SupportCaseListResponse:
        stmt = select(SupportCase)
        if status:
            stmt = stmt.where(SupportCase.status == status)
        if user_id:
            stmt = stmt.where(SupportCase.user_id == user_id)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = await self.db.scalar(count_stmt) or 0

        stmt = stmt.order_by(SupportCase.created_at.desc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(stmt)
        items = [SupportCaseItem.model_validate(row) for row in result.scalars().all()]

        return SupportCaseListResponse(items=items, total=total, page=page, page_size=page_size)

    async def update_case(self, case_id: str, payload: SupportCaseUpdateRequest) -> SupportCaseItem:
        stmt = select(SupportCase).where(SupportCase.id == case_id)
        result = await self.db.execute(stmt)
        case = result.scalar_one_or_none()
        if not case:
            raise HTTPException(status_code=404, detail="Support case not found")

        updates = payload.model_dump(exclude_unset=True)
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        for field, value in updates.items():
            setattr(case, field, value)

        await self.db.commit()
        await self.db.refresh(case)
        return SupportCaseItem.model_validate(case)

    async def delete_case(self, case_id: str) -> None:
        stmt = select(SupportCase).where(SupportCase.id == case_id)
        result = await self.db.execute(stmt)
        case = result.scalar_one_or_none()
        if not case:
            raise HTTPException(status_code=404, detail="Support case not found")
        await self.db.delete(case)
        await self.db.commit()

    # ------------------------------------------------------------------ #
    async def create_or_update_conversation(
        self,
        payload: SupportConversationCreateRequest,
    ) -> SupportConversationCreateResponse:
        """只记录会话状态，不持久化聊天内容。"""
        await self._build_user_profile(payload.user_id)

        existing = await self._get_status_record(payload.openim_conversation_id)
        if existing:
            existing.status = "pending"
            existing.peer_user_id = existing.peer_user_id or payload.user_id
            existing.updated_at = datetime.utcnow()
        else:
            existing = SupportChatStatus(
                conversation_id=payload.openim_conversation_id,
                peer_user_id=payload.user_id,
                status="pending",
            )
            self.db.add(existing)

        await self.db.commit()
        return SupportConversationCreateResponse(
            conversation_id=payload.openim_conversation_id,
            status=existing.status,
        )

    # ------------------------------------------------------------------ #
    async def list_conversations(
        self,
        query: SupportConversationQuery,
    ) -> SupportConversationListResponse:
        """从OpenIM拉取会话列表并与本地状态合并。"""

        openim_data = await openim_service.get_sorted_conversation_list(
            owner_user_id=settings.OPENIM_ADMIN_USER_ID,
            page_number=query.page,
            page_size=query.page_size,
        )
        if not openim_data:
            raise HTTPException(status_code=502, detail="OpenIM 会话列表不可用")

        conversation_elems = openim_data.get("conversationElems") or []
        conversation_ids = [elem.get("conversationID") for elem in conversation_elems if elem.get("conversationID")]
        status_map = await self._get_status_map(conversation_ids)

        peer_user_ids: Set[str] = set()
        parsed_rows = []
        for elem in conversation_elems:
            conv_id = elem.get("conversationID")
            if not conv_id:
                continue
            msg_info = elem.get("msgInfo") or {}
            peer_user_id = self._extract_peer_user_id(conv_id, msg_info)
            if peer_user_id:
                peer_user_ids.add(peer_user_id)

            status_row = status_map.get(conv_id)
            status_value = status_row.status if status_row else "pending"
            last_message, last_message_at = self._extract_latest_message(msg_info)

            parsed_rows.append(
                {
                    "conversation_id": conv_id,
                    "peer_user_id": peer_user_id,
                    "status": status_value,
                    "last_message": last_message,
                    "last_message_at": last_message_at,
                }
            )

        profiles = await self._build_bulk_profiles(peer_user_ids)

        def _match_filters(row_profile: Optional[SupportConversationUserProfile], row_status: str, peer_user_id: Optional[str]) -> bool:
            if query.status and row_status != query.status:
                return False
            if query.uid and (not peer_user_id or query.uid.lower() not in peer_user_id.lower()):
                return False
            if query.username and (not row_profile or not row_profile.username or query.username.lower() not in row_profile.username.lower()):
                return False
            if query.display_name and (not row_profile or not row_profile.display_name or query.display_name.lower() not in row_profile.display_name.lower()):
                return False
            if query.wallet_address and (not row_profile or not row_profile.wallet_address or query.wallet_address.lower() not in row_profile.wallet_address.lower()):
                return False
            return True

        items: List[SupportConversationListItem] = []
        for row in parsed_rows:
            profile = profiles.get(row["peer_user_id"])
            if not _match_filters(profile, row["status"], row["peer_user_id"]):
                continue

            items.append(
                SupportConversationListItem(
                    conversation_id=row["conversation_id"],
                    openim_conversation_id=row["conversation_id"],
                    user_id=row["peer_user_id"] or "",
                    username=profile.username if profile else None,
                    display_name=profile.display_name if profile else None,
                    wallet_address=profile.wallet_address if profile else None,
                    status=row["status"],
                    last_message=row["last_message"],
                    last_message_at=row["last_message_at"],
                    app_version=profile.app_version if profile else None,
                )
            )

        total_raw = openim_data.get("conversationTotal")
        try:
            total_from_openim = int(total_raw) if total_raw is not None else len(conversation_elems)
        except (TypeError, ValueError):
            total_from_openim = len(conversation_elems)
        has_filters = any([
            query.status,
            query.uid,
            query.username,
            query.display_name,
            query.wallet_address,
        ])

        return SupportConversationListResponse(
            items=items,
            total=len(items) if has_filters else total_from_openim,
            page=query.page,
            page_size=query.page_size,
        )

    # ------------------------------------------------------------------ #
    async def get_conversation_detail(self, conversation_id: str) -> SupportConversationDetailResponse:
        status_row = await self._get_status_record(conversation_id)
        peer_user_id = status_row.peer_user_id if status_row else self._extract_peer_user_id(conversation_id, None)

        profile = None
        if peer_user_id:
            try:
                profile = await self._build_user_profile(peer_user_id)
            except HTTPException:
                profile = None

        if not profile:
            raise HTTPException(status_code=404, detail="Conversation user not found")

        return SupportConversationDetailResponse(
            conversation_id=conversation_id,
            openim_conversation_id=conversation_id,
            status=status_row.status if status_row else "pending",
            last_message=None,
            last_message_at=None,
            messages=[],  # 不持久化消息，需实时从OpenIM拉取时再补充
            user_profile=profile,
        )

    # ------------------------------------------------------------------ #
    async def update_status(
        self,
        conversation_id: str,
        payload: SupportConversationStatusUpdateRequest,
        operator_id: str,
        operator_name: str,
    ) -> None:
        status_row = await self._get_status_record(conversation_id)
        if not status_row:
            status_row = SupportChatStatus(
                conversation_id=conversation_id,
                peer_user_id=self._extract_peer_user_id(conversation_id, None),
                status=payload.status,
            )
            self.db.add(status_row)

        resolved_operator_name = await _resolve_operator_display_name(self.db, operator_id, operator_name)
        status_row.status = payload.status
        status_row.updated_by = operator_id
        status_row.updated_by_name = resolved_operator_name
        status_row.updated_at = datetime.utcnow()

        await self.db.commit()

        await self.audit_service.log_action(
            operator_id=operator_id,
            action_type="support_conversation_status_update",
            target_type="support_conversation",
            target_id=conversation_id,
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
    async def _get_status_record(self, conversation_id: str) -> SupportChatStatus | None:
        stmt = select(SupportChatStatus).where(SupportChatStatus.conversation_id == conversation_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_status_map(self, conversation_ids: List[str]) -> Dict[str, SupportChatStatus]:
        if not conversation_ids:
            return {}

        stmt = select(SupportChatStatus).where(SupportChatStatus.conversation_id.in_(conversation_ids))
        result = await self.db.execute(stmt)
        rows = result.scalars().all()
        return {row.conversation_id: row for row in rows}

    def _extract_peer_user_id(self, conversation_id: Optional[str], msg_info: Optional[Dict[str, Any]]) -> Optional[str]:
        admin_id = settings.OPENIM_ADMIN_USER_ID

        if conversation_id:
            parts = [p for p in conversation_id.split("_") if p]
            for part in parts:
                if part.lower() in {"si", "single", "sg"}:
                    continue
                if part != admin_id:
                    return part

        if msg_info:
            for key in ("sendID", "recvID", "userID"):
                value = msg_info.get(key)
                if value and value != admin_id:
                    return value

        return None

    def _extract_latest_message(self, msg_info: Dict[str, Any]) -> tuple[Optional[str], Optional[datetime]]:
        if not msg_info:
            return None, None

        content_raw = msg_info.get("content")
        text_content: Optional[str] = None
        if isinstance(content_raw, str):
            try:
                parsed = json.loads(content_raw)
                text_content = parsed.get("content") or parsed.get("text")
            except json.JSONDecodeError:
                text_content = content_raw
        elif isinstance(content_raw, dict):
            text_content = content_raw.get("content") or content_raw.get("text")

        ts_ms = (
            msg_info.get("LatestMsgRecvTime")
            or msg_info.get("sendTime")
            or msg_info.get("createTime")
        )
        timestamp = datetime.fromtimestamp(ts_ms / 1000) if ts_ms else None

        return text_content, timestamp

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

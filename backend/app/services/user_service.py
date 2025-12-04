"""User service layer - adapted for existing database schema."""
from datetime import datetime, timedelta
from typing import Optional
import uuid
import zlib
import logging
import jwt

import httpx
from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.user import Author, Ban, User, UserWallet
from app.models.ban_history import BanHistory
from app.schemas.user import (
    AuthorResponse,
    BanHistoryItem,
    BanHistoryListResponse,
    BanRequest,
    UnbanRequest,
    UserDetailResponse,
    UserListItemResponse,
    UserListResponse,
    UserResponse,
    UserSearchParams,
    UserUpdate,
    WalletResponse,
    TokenResponse,
)
from app.services.audit_service import AuditService
from app.services.notification_service import notification_service

logger = logging.getLogger(__name__)


class UserService:
    """User service."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.notification_service = notification_service
        self.audit_service = AuditService(db)
        self.uid_salt = settings.AGORA_UID_SALT or "JyzuC2!EPq8@EvF-zdqjdsh6NTpkr_nz"
        self.MAX_UID = 2_147_483_647

    def _resolve_operator_id(self, preferred_id: Optional[str]) -> str:
        if preferred_id:
            return preferred_id
        raise HTTPException(status_code=401, detail="Operator id not provided")

    async def _resolve_operator_name(self, operator_id: str) -> str:
        """根据操作员ID反查作者表，找不到时回退到 operator_id。"""
        if not operator_id:
            return ""

        stmt = select(Author.username).where(Author.id == operator_id)
        username = await self.db.scalar(stmt)
        if username:
            return username

        return operator_id

    def _generate_agora_uid(self, user_id: str) -> int:
        """Generate deterministic Agora UID."""
        salted_input = f"{self.uid_salt}:{user_id}"
        crc32_hash = zlib.crc32(salted_input.encode("utf-8")) & 0xFFFFFFFF
        uid = (crc32_hash % (self.MAX_UID - 1)) + 1
        return uid

    async def _get_superuser_token(self) -> str:
        """从 accesstoken 表获取最新的超管 token，用于外部接口调用。"""
        stmt = (
            select(text('token'))
            .select_from(text('accesstoken'))
            .where(text("user_id = 'BgwSdhW0z60'"))
            .order_by(text('created_at DESC'))
            .limit(1)
        )
        result = await self.db.execute(stmt)
        token = result.scalar_one_or_none()
        if not token:
            logger.error("accesstoken表未找到超管token，无法调用外部接口")
            await self.db.rollback()
            raise HTTPException(status_code=500, detail="未找到可用的超管token")

        logger.warning("外部调用使用accesstoken表token=%s", token)
        return token

    async def get_users(self, params: UserSearchParams) -> UserListResponse:
        """Get user list with search and pagination - joining users, authors, and wallets."""

        # Build base query joining users with authors
        query = select(User).options(
            selectinload(User.author),
            selectinload(User.wallets),
            selectinload(User.bans)
        )

        # Apply filters
        filters = []

        if params.user_id:
            filters.append(User.id == params.user_id)

        if params.email:
            filters.append(User.email.ilike(f"%{params.email}%"))

        if params.phone_number:
            filters.append(User.phone_number.ilike(f"%{params.phone_number}%"))

        if params.status:
            filters.append(User.status == params.status)

        if params.is_active is not None:
            filters.append(User.is_active == params.is_active)

        if params.region:
            filters.append(User.region == params.region)

        # Username / display name search (in authors table)
        author_conditions = []
        if params.username:
            author_conditions.append(Author.username.ilike(f"%{params.username}%"))
        if params.display_name:
            author_conditions.append(Author.name.ilike(f"%{params.display_name}%"))
        if author_conditions:
            author_subquery = select(Author.user_id).where(or_(*author_conditions))
            filters.append(User.id.in_(author_subquery))

        # Wallet address search (in user_wallet table)
        if params.wallet_address:
            wallet_subquery = select(UserWallet.user_id).where(
                UserWallet.pubkey.ilike(f"%{params.wallet_address}%")
            )
            filters.append(User.id.in_(wallet_subquery))

        if filters:
            query = query.where(and_(*filters))

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total = await self.db.scalar(count_query) or 0

        # Apply sorting
        sort_column = getattr(User, params.sort_by, User.created_at)
        if params.sort_order == "desc":
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

        # Apply pagination
        offset = (params.page - 1) * params.page_size
        query = query.offset(offset).limit(params.page_size)

        # Execute query
        result = await self.db.execute(query)
        users = result.scalars().all()

        # Build response
        items: list[UserListItemResponse] = []
        for user in users:
            wallet_models = [WalletResponse.model_validate(w) for w in user.wallets]
            bsc_wallet = next((w.pubkey for w in wallet_models if w.type == "bsc"), None)

            items.append(
                UserListItemResponse(
                    user_id=user.id,
                    username=user.author.username if user.author else None,
                    display_name=user.author.name if user.author else None,
                    created_at=user.created_at,
                    bsc_wallet=bsc_wallet,
                    email=user.author.email if user.author else None,
                    phone_number=user.author.phone_number if user.author else None,
                    status=user.status,
                )
            )

        return UserListResponse(
            items=items,
            total=total,
            page=params.page,
            page_size=params.page_size
        )

    async def get_user_detail(self, user_id: str) -> UserDetailResponse:
        """Get user detail with author and wallet information."""
        query = select(User).where(User.id == user_id).options(
            selectinload(User.author),
            selectinload(User.wallets),
        )
        result = await self.db.execute(query)
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        wallet_models = [WalletResponse.model_validate(w) for w in user.wallets]
        author_user_id = user.author.user_id if user.author else user.id

        im_id = None
        try:
            im_result = await self.db.execute(
                text("SELECT im_id FROM toci_im WHERE toci_id = :toci_id LIMIT 1"),
                {"toci_id": author_user_id},
            )
            im_id = im_result.scalar_one_or_none()
        except Exception:
            im_id = None

        role = None
        try:
            role_result = await self.db.execute(
                text("SELECT name FROM permissions WHERE author_id = :author_id LIMIT 1"),
                {"author_id": author_user_id},
            )
            role = role_result.scalar_one_or_none()
        except Exception:
            role = None

        agora_id = self._generate_agora_uid(user.id)

        return UserDetailResponse(
            user=UserResponse.model_validate(user),
            author=AuthorResponse.model_validate(user.author) if user.author else None,
            wallets=wallet_models,
            im_id=im_id,
            role=role,
            agora_id=agora_id,
            app_version="",
            yidun_task_id="",
        )

    async def get_ban_history(
        self,
        user_id: str,
        page: int,
        size: int,
    ) -> BanHistoryListResponse:
        if page < 1 or size < 1:
            raise HTTPException(status_code=400, detail="Invalid pagination parameters")

        query = select(BanHistory).where(BanHistory.user_id == user_id)
        count_stmt = select(func.count()).select_from(query.subquery())
        total = await self.db.scalar(count_stmt) or 0

        stmt = (
            query.order_by(BanHistory.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        result = await self.db.execute(stmt)
        ban_items = [BanHistoryItem.model_validate(row) for row in result.scalars().all()]

        # 运营平台要求展示操作者的可读名称，这里使用 operator_id 反查 authors.username
        operator_ids = {item.operator_id for item in ban_items if item.operator_id}
        operator_name_map: dict[str, Optional[str]] = {}
        if operator_ids:
            name_stmt = select(Author.id, Author.username).where(Author.id.in_(operator_ids))
            name_result = await self.db.execute(name_stmt)
            operator_name_map = {row[0]: row[1] for row in name_result.all()}

        items = [
            item.model_copy(
                update={
                    "operator_name": operator_name_map.get(item.operator_id) or item.operator_name or item.operator_id
                }
            )
            for item in ban_items
        ]

        return BanHistoryListResponse(items=items, total=total, page=page, size=size)

    async def update_user(
        self,
        user_id: str,
        user_data: UserUpdate,
        operator_id: str,
        operator_name: str,
    ) -> UserResponse:
        """Update mutable user fields."""
        payload = user_data.model_dump(exclude_unset=True)

        if not payload:
            raise HTTPException(status_code=400, detail="No fields provided for update")

        query = select(User).where(User.id == user_id)
        result = await self.db.execute(query)
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        for field, value in payload.items():
            setattr(user, field, value)

        user.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(user)

        # Audit log
        resolved_operator_id = self._resolve_operator_id(operator_id)
        resolved_operator_name = await self._resolve_operator_name(resolved_operator_id)

        await self.audit_service.log_action(
            operator_id=resolved_operator_id,
            action_type="update_user",
            target_type="user",
            target_id=user_id,
            action_details={**payload, "operator_name": resolved_operator_name},
        )

        return UserResponse.model_validate(user)

    async def ban_user(
        self,
        user_id: str,
        ban_data: BanRequest,
        operator_id: str,
        operator_name: str,
        authorization_header: str,
    ) -> None:
        """Ban user account."""
        if ban_data is None:
            raise HTTPException(status_code=400, detail="Ban payload is required")

        # Get user
        query = select(User).where(User.id == user_id)
        result = await self.db.execute(query)
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Check if user already has an active ban
        active_ban_query = select(Ban).where(
            and_(
                Ban.user_id == user_id,
                Ban.revoked_at.is_(None),
                or_(
                    Ban.ends_at.is_(None),  # Permanent ban
                    Ban.ends_at > datetime.utcnow()  # Future end time
                )
            )
        )
        existing_ban = await self.db.scalar(active_ban_query)

        if existing_ban:
            raise HTTPException(status_code=400, detail="User already has an active ban")

        # Calculate ban end time (duration is in seconds)
        ends_at = None
        if ban_data.duration:
            ends_at = datetime.utcnow() + timedelta(seconds=ban_data.duration)

        resolved_operator_id = self._resolve_operator_id(operator_id)
        resolved_operator_name = await self._resolve_operator_name(resolved_operator_id)

        # Create ban record
        ban = Ban(
            id=str(uuid.uuid4()),
            user_id=user_id,
            reason=ban_data.reason,
            ends_at=ends_at,
            imposed_by=resolved_operator_id,
            created_at=datetime.utcnow()
        )
        self.db.add(ban)

        # Record history entry within same transaction
        history_entry = BanHistory(
            user_id=user_id,
            action="ban",
            reason=ban_data.reason,
            duration_seconds=ban_data.duration,
            operator_id=resolved_operator_id,
            ban_method=ban_data.ban_method,
            operator_name=resolved_operator_name,
            created_at=datetime.utcnow()
        )
        self.db.add(history_entry)

        await self.db.flush()

        await self._call_external_ban_api(user_id, ban_data)

        await self.db.commit()

        # Send notification via external notification API
        try:
            await self.notification_service.send_user_banned_notification(
                user_id=user_id,
                reason=ban_data.reason,
                ends_at=ends_at.isoformat() if ends_at else None
            )
        except Exception as e:
            # Log but don't fail the ban operation
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to send ban notification: {e}")

        # Audit log
        await self.audit_service.log_action(
            operator_id=resolved_operator_id,
            action_type="ban_user",
            target_type="user",
            target_id=user_id,
            action_details={
                "reason": ban_data.reason,
                "duration_seconds": ban_data.duration,
                "ends_at": ends_at.isoformat() if ends_at else None,
                "notify": ban_data.notify,
                "ban_method": ban_data.ban_method,
                "operator_name": resolved_operator_name,
            }
        )

    async def unban_user(
        self,
        user_id: str,
        unban_data: Optional[UnbanRequest],
        operator_id: str,
        operator_name: str,
        authorization_header: str,
    ) -> None:
        """Unban user account."""
        # Get user
        query = select(User).where(User.id == user_id)
        result = await self.db.execute(query)
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Find active ban
        active_ban_query = select(Ban).where(
            and_(
                Ban.user_id == user_id,
                Ban.revoked_at.is_(None)
            )
        )
        result = await self.db.execute(active_ban_query)
        active_bans = result.scalars().all()

        resolved_operator_id = self._resolve_operator_id(operator_id)
        resolved_operator_name = await self._resolve_operator_name(resolved_operator_id)

        unban_reason = unban_data.reason if unban_data and unban_data.reason else "Unbanned by operator"

        if not active_bans:
            # Idempotent unban: if user status is banned but no active ban rows, still allow unban to proceed
            if user.status == "banned":
                user.status = "active"
                user.updated_at = datetime.utcnow()

                history_entry = BanHistory(
                    user_id=user_id,
                    action="unban",
                    reason=unban_reason,
                    duration_seconds=None,
                    operator_id=resolved_operator_id,
                    ban_method=None,
                    operator_name=resolved_operator_name,
                    created_at=datetime.utcnow(),
                )
                self.db.add(history_entry)

                await self._call_external_unban_api(user_id, unban_reason, authorization_header)
                await self.db.commit()

                await self.audit_service.log_action(
                    operator_id=resolved_operator_id,
                    action_type="unban_user",
                    target_type="user",
                    target_id=user_id,
                    action_details={
                        "reason": unban_reason,
                        "bans_revoked": 0,
                        "operator_name": resolved_operator_name,
                    }
                )
                return

            raise HTTPException(status_code=400, detail="User has no active bans")

        # Revoke all active bans
        for ban in active_bans:
            ban.revoked_at = datetime.utcnow()
            ban.revoked_by = resolved_operator_id
            ban.revoke_reason = unban_reason

        history_entry = BanHistory(
            user_id=user_id,
            action="unban",
            reason=unban_reason,
            duration_seconds=None,
            operator_id=resolved_operator_id,
            ban_method=None,
            operator_name=resolved_operator_name,
            created_at=datetime.utcnow(),
        )
        self.db.add(history_entry)

        await self.db.flush()

        await self._call_external_unban_api(user_id, unban_reason)

        await self.db.commit()

        # Send unban notification via external notification API
        try:
            await self.notification_service.send_user_unbanned_notification(
                user_id=user_id,
                reason=unban_reason
            )
        except Exception as e:
            # Log but don't fail the unban operation
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to send unban notification: {e}")

        # Audit log
        await self.audit_service.log_action(
            operator_id=resolved_operator_id,
            action_type="unban_user",
            target_type="user",
            target_id=user_id,
            action_details={
                "reason": unban_reason,
                "bans_revoked": len(active_bans),
                "operator_name": resolved_operator_name,
            }
        )

    async def _call_external_ban_api(
        self,
        user_id: str,
        ban_data: BanRequest,
    ) -> None:
        """调用外部封禁接口，确保与上游系统同步。"""
        api_url = settings.EXTERNAL_USER_API_URL
        if not api_url:
            await self.db.rollback()
            raise HTTPException(status_code=500, detail="外部封禁接口未配置")

        token = await self._get_superuser_token()

        endpoint = f"{api_url.rstrip('/')}/users/{user_id}/ban?role=write"
        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        payload = {
            "reason": ban_data.reason,
            "duration": ban_data.duration or 0,
        }

        timeout = httpx.Timeout(connect=5.0, read=45.0, write=10.0, pool=5.0)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    endpoint,
                    json=payload,
                    headers=headers,
                )

            if response.status_code != 200:
                logger.error(
                    "外部封禁接口返回异常 status=%s body=%s endpoint=%s payload=%s headers=%s token=%s",
                    response.status_code,
                    response.text[:500],
                    endpoint,
                    payload,
                    {k: v for k, v in headers.items() if k.lower() != "authorization"},
                    token,
                )
                await self.db.rollback()
                raise HTTPException(
                    status_code=502,
                    detail=f"外部封禁接口返回异常状态: {response.status_code}",
                )

        except HTTPException:
            raise
        except Exception as exc:
            logger.exception(
                "调用外部封禁接口失败 endpoint=%s payload=%s headers=%s token=%s",
                endpoint,
                payload,
                {k: v for k, v in headers.items() if k.lower() != "authorization"},
                token,
            )
            await self.db.rollback()
            raise HTTPException(
                status_code=502,
                detail=f"调用外部封禁接口失败: {exc}",
            ) from exc

    async def _call_external_unban_api(
        self,
        user_id: str,
        reason: Optional[str],
    ) -> None:
        """调用外部解封接口，确保状态一致。"""
        api_url = settings.EXTERNAL_USER_API_URL
        if not api_url:
            await self.db.rollback()
            raise HTTPException(status_code=500, detail="外部解封接口未配置")

        token = await self._get_superuser_token()

        endpoint = f"{api_url.rstrip('/')}/users/{user_id}/unban?role=write"
        headers = {
            "accept": "application/json",
            "Authorization": f"Bearer {token}",
        }
        payload = {"reason": reason} if reason else None
        request_kwargs = {
            "headers": headers,
        }
        if payload is not None:
            headers["Content-Type"] = "application/json"
            request_kwargs["json"] = payload

        timeout = httpx.Timeout(connect=5.0, read=45.0, write=10.0, pool=5.0)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(endpoint, **request_kwargs)

            if response.status_code != 200:
                logger.error(
                    "外部解封接口返回异常 status=%s body=%s endpoint=%s payload=%s headers=%s token=%s",
                    response.status_code,
                    response.text[:500],
                    endpoint,
                    payload,
                    {k: v for k, v in headers.items() if k.lower() != "authorization"},
                    token,
                )
                await self.db.rollback()
                raise HTTPException(
                    status_code=502,
                    detail=f"外部解封接口返回异常状态: {response.status_code}",
                )

        except HTTPException:
            raise
        except Exception as exc:
            logger.exception(
                "调用外部解封接口失败 endpoint=%s payload=%s headers=%s token=%s",
                endpoint,
                payload,
                {k: v for k, v in headers.items() if k.lower() != "authorization"},
                token,
            )
            await self.db.rollback()
            raise HTTPException(
                status_code=502,
                detail=f"调用外部解封接口失败: {exc}",
            ) from exc

    # ------------------------------------------------------------------ #
    def generate_superuser_token(
        self,
        user_id: str,
        expires_minutes: int = 60,
        audience: Optional[str] = None,
        extra_claims: Optional[dict] = None,
        secret: Optional[str] = None,
        algorithm: Optional[str] = None,
        aud_is_list: bool = True,
        include_is_superuser: bool = False,
    ) -> TokenResponse:
        """
        生成用于外部封禁/解封接口的超级管理员 JWT。

        - 仅包含 sub/aud/iat/exp，aud 使用列表以兼容 fastapi-users 默认策略
        - 使用可配置的外部密钥/算法
        """
        now = datetime.utcnow()
        exp = now + timedelta(minutes=expires_minutes)
        aud_value = audience or "fastapi-users:auth"
        aud_claim = [aud_value] if (aud_is_list and isinstance(aud_value, str)) else aud_value
        signing_secret = secret or settings.JWT_SECRET_KEY
        signing_alg = algorithm or settings.JWT_ALGORITHM

        claims = {
            "sub": user_id,
            "aud": aud_claim,
            "iat": int(now.timestamp()),
            "exp": int(exp.timestamp()),
        }
        if include_is_superuser:
            claims["is_superuser"] = True
        if extra_claims:
            for k, v in extra_claims.items():
                if k in {"sub", "aud", "iat", "exp"}:
                    continue
                claims[k] = v

        token = jwt.encode(
            claims,
            signing_secret,
            algorithm=signing_alg,
        )
        if isinstance(token, bytes):
            token = token.decode("utf-8")

        return TokenResponse(token=token, expires_at=exp, token_type="bearer")

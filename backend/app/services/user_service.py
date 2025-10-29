"""User service layer - adapted for existing database schema."""
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy import select, or_, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload
from fastapi import HTTPException
from app.models.user import User, Author, UserWallet, Ban
from app.schemas.user import (
    UserSearchParams,
    UserListResponse,
    UserDetailResponse,
    UserResponse,
    AuthorResponse,
    WalletResponse,
    BanRequest,
    UnbanRequest,
    BanResponse,
    UserUpdate
)
from app.services.notification_service import notification_service
from app.services.audit_service import AuditService
import uuid


class UserService:
    """User service."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.notification_service = notification_service
        self.audit_service = AuditService(db)

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

        # Username search (in authors table)
        if params.username:
            author_subquery = select(Author.user_id).where(
                Author.username.ilike(f"%{params.username}%")
            )
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
        items = []
        for user in users:
            # Get active bans
            active_bans = [
                BanResponse(
                    id=ban.id,
                    user_id=ban.user_id,
                    reason=ban.reason,
                    ends_at=ban.ends_at,
                    imposed_by=ban.imposed_by,
                    revoked_at=ban.revoked_at,
                    revoked_by=ban.revoked_by,
                    revoke_reason=ban.revoke_reason,
                    created_at=ban.created_at,
                    is_active=(ban.revoked_at is None and (ban.ends_at is None or ban.ends_at > datetime.utcnow()))
                )
                for ban in user.bans
                if ban.revoked_at is None and (ban.ends_at is None or ban.ends_at > datetime.utcnow())
            ]

            items.append(UserDetailResponse(
                user=UserResponse.model_validate(user),
                author=AuthorResponse.model_validate(user.author) if user.author else None,
                wallets=[WalletResponse.model_validate(w) for w in user.wallets],
                active_bans=active_bans
            ))

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
            selectinload(User.bans)
        )
        result = await self.db.execute(query)
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Get active bans
        active_bans = [
            BanResponse(
                id=ban.id,
                user_id=ban.user_id,
                reason=ban.reason,
                ends_at=ban.ends_at,
                imposed_by=ban.imposed_by,
                revoked_at=ban.revoked_at,
                revoked_by=ban.revoked_by,
                revoke_reason=ban.revoke_reason,
                created_at=ban.created_at,
                is_active=(ban.revoked_at is None and (ban.ends_at is None or ban.ends_at > datetime.utcnow()))
            )
            for ban in user.bans
            if ban.revoked_at is None
        ]

        return UserDetailResponse(
            user=UserResponse.model_validate(user),
            author=AuthorResponse.model_validate(user.author) if user.author else None,
            wallets=[WalletResponse.model_validate(w) for w in user.wallets],
            active_bans=active_bans
        )

    async def update_user(self, user_id: str, user_data: UserUpdate) -> UserResponse:
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
        await self.audit_service.log_action(
            operator_id="admin",  # TODO: replace with authenticated operator
            action_type="update_user",
            target_type="user",
            target_id=user_id,
            action_details=payload,
        )

        return UserResponse.model_validate(user)

    async def ban_user(
        self,
        user_id: str,
        ban_data: BanRequest,
        operator_id: str
    ) -> None:
        """Ban user account."""
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

        # Create ban record
        ban = Ban(
            id=str(uuid.uuid4()),
            user_id=user_id,
            reason=ban_data.reason,
            ends_at=ends_at,
            imposed_by=operator_id,
            created_at=datetime.utcnow()
        )
        self.db.add(ban)

        # Update user status to 'banned'
        user.status = "banned"
        user.updated_at = datetime.utcnow()

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
            operator_id=operator_id,
            action_type="ban_user",
            target_type="user",
            target_id=user_id,
            action_details={
                "reason": ban_data.reason,
                "duration_seconds": ban_data.duration,
                "ends_at": ends_at.isoformat() if ends_at else None,
                "notify": ban_data.notify
            }
        )

    async def unban_user(
        self,
        user_id: str,
        unban_data: Optional[UnbanRequest],
        operator_id: str
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

        if not active_bans:
            raise HTTPException(status_code=400, detail="User has no active bans")

        # Revoke all active bans
        unban_reason = unban_data.reason if unban_data and unban_data.reason else "Unbanned by operator"
        for ban in active_bans:
            ban.revoked_at = datetime.utcnow()
            ban.revoked_by = operator_id
            ban.revoke_reason = unban_reason

        # Update user status to 'active'
        user.status = "active"
        user.updated_at = datetime.utcnow()

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
            operator_id=operator_id,
            action_type="unban_user",
            target_type="user",
            target_id=user_id,
            action_details={
                "reason": unban_reason,
                "bans_revoked": len(active_bans)
            }
        )

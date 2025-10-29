"""Audit service for logging operator actions."""
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.audit import OperatorAuditLog
import logging

logger = logging.getLogger(__name__)


class AuditService:
    """Audit service for logging operator actions."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def log_action(
        self,
        operator_id,
        action_type: str,
        target_type: str = None,
        target_id = None,
        action_details: dict = None,
        ip_address: str = None,
        user_agent: str = None
    ) -> None:
        """
        Log operator action.

        Args:
            operator_id: ID of the operator performing the action
            action_type: Type of action (ban_user, approve_meme, etc.)
            target_type: Type of target (user, meme, post, etc.)
            target_id: ID of the target
            action_details: Additional details as JSON
            ip_address: IP address of the operator
            user_agent: User agent string
        """
        try:
            if not operator_id:
                raise ValueError("operator_id is required for audit logging")

            audit_log = OperatorAuditLog(
                operator_id=str(operator_id),
                action_type=action_type,
                target_type=target_type,
                target_id=str(target_id) if target_id is not None else None,
                action_details=action_details,
                ip_address=ip_address,
                user_agent=user_agent,
                created_at=datetime.utcnow()
            )

            self.db.add(audit_log)
            await self.db.commit()

            logger.info(
                f"Audit log created: operator={operator_id}, "
                f"action={action_type}, target={target_type}:{target_id}"
            )

        except Exception as e:
            logger.error(f"Error creating audit log: {e}")
            # Don't raise exception to avoid breaking the main flow

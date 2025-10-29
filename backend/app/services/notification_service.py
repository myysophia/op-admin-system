"""External notification service for meme review notifications."""
import httpx
import logging
from typing import List, Dict, Any, Optional
from app.config import settings

logger = logging.getLogger(__name__)


class NotificationService:
    """External notification service."""

    def __init__(self):
        self.api_url = settings.NOTIFICATION_API_URL
        self.timeout = 10.0

    async def send_notification(
        self,
        recipients_ids: List[str],
        notification_type: str,
        meta: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Send notification to users via external notification API.

        Args:
            recipients_ids: List of recipient user IDs
            notification_type: Type of notification (e.g., "meme_approved", "meme_rejected")
            meta: Additional metadata for the notification

        Returns:
            True if sent successfully, False otherwise
        """
        if not recipients_ids:
            logger.warning("No recipients provided for notification")
            return False

        payload_meta = dict(meta or {})  # copy to avoid mutating caller

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_url}?role=write",
                    headers={
                        "accept": "application/json",
                        "Content-Type": "application/json"
                    },
                    json={
                        "recipients_ids": recipients_ids,
                        "notification_base": {
                            "type": notification_type,
                            "meta": payload_meta
                        }
                    },
                    timeout=self.timeout
                )

                if response.status_code == 200:
                    logger.info(
                        f"Notification sent successfully: type={notification_type}, "
                        f"recipients={len(recipients_ids)}"
                    )
                    return True
                else:
                    logger.error(
                        f"Failed to send notification: status={response.status_code}, "
                        f"response={response.text}"
                    )
                    return False

        except httpx.TimeoutException:
            logger.error(f"Notification API timeout after {self.timeout}s")
            return False
        except Exception as e:
            logger.error(f"Error sending notification: {e}")
            return False

    async def send_meme_approved_notification(
        self,
        user_id: str,
        meme_name: str,
        meme_symbol: str,
        order_id: str,
        comment: Optional[str] = None
    ) -> bool:
        """
        Send meme approval notification to creator.

        Args:
            user_id: Creator user ID
            meme_name: Meme name
            meme_symbol: Meme symbol
            order_id: Order ID
            comment: Optional review comment

        Returns:
            True if sent successfully
        """
        meta = {
            "meme_name": meme_name,
            "meme_symbol": meme_symbol,
            "order_id": order_id,
            "status": "approved"
        }

        if comment:
            meta["comment"] = comment

        return await self.send_notification(
            recipients_ids=[user_id],
            notification_type="meme_approved",
            meta=meta
        )

    async def send_meme_rejected_notification(
        self,
        user_id: str,
        meme_name: str,
        meme_symbol: str,
        order_id: str,
        reason: Optional[str] = None
    ) -> bool:
        """
        Send meme rejection notification to creator.

        Args:
            user_id: Creator user ID
            meme_name: Meme name
            meme_symbol: Meme symbol
            order_id: Order ID
            reason: Optional rejection reason

        Returns:
            True if sent successfully
        """
        meta = {
            "meme_name": meme_name,
            "meme_symbol": meme_symbol,
            "order_id": order_id,
            "status": "rejected"
        }

        if reason:
            meta["reason"] = reason

        return await self.send_notification(
            recipients_ids=[user_id],
            notification_type="meme_rejected",
            meta=meta
        )

    async def send_user_banned_notification(
        self,
        user_id: str,
        reason: str,
        ends_at: Optional[str] = None
    ) -> bool:
        """
        Send ban notification to user.

        Args:
            user_id: User ID
            reason: Ban reason
            ends_at: Ban end time (None for permanent)

        Returns:
            True if sent successfully
        """
        meta = {
            "reason": reason,
            "is_permanent": ends_at is None
        }

        if ends_at:
            meta["ends_at"] = ends_at

        return await self.send_notification(
            recipients_ids=[user_id],
            notification_type="user_banned",
            meta=meta
        )

    async def send_user_unbanned_notification(
        self,
        user_id: str,
        reason: Optional[str] = None
    ) -> bool:
        """
        Send unban notification to user.

        Args:
            user_id: User ID
            reason: Optional reason for unbanning

        Returns:
            True if sent successfully
        """
        meta = {}
        if reason:
            meta["reason"] = reason

        return await self.send_notification(
            recipients_ids=[user_id],
            notification_type="user_unbanned",
            meta=meta
        )


# Global instance
notification_service = NotificationService()

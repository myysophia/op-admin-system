"""OpenIM integration service for chat functionality."""
import httpx
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from app.config import settings

logger = logging.getLogger(__name__)


class OpenIMService:
    """OpenIM service for chat messaging integration."""

    def __init__(self):
        self.api_url = settings.OPENIM_API_URL
        self.ws_url = settings.OPENIM_WS_URL
        self.secret = settings.OPENIM_SECRET
        self.admin_user_id = settings.OPENIM_ADMIN_USER_ID
        self.platform_id = settings.OPENIM_PLATFORM_ID

    async def get_token(self, user_id: str = None) -> Optional[str]:
        """
        Get token from OpenIM.

        Args:
            user_id: User ID (defaults to admin user)

        Returns:
            Token string if successful
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_url}/auth/user_token",
                    json={
                        "secret": self.secret,
                        "platform_id": self.platform_id,
                        "user_id": user_id or self.admin_user_id
                    },
                    timeout=10.0
                )
                if response.status_code == 200:
                    data = response.json()
                    return data.get("data", {}).get("token")
                else:
                    logger.error(f"Failed to get token: {response.text}")
        except Exception as e:
            logger.error(f"Error getting OpenIM token: {e}")
        return None

    async def send_message(
        self,
        from_user_id: str,
        to_user_id: str,
        content: str,
        content_type: int = 101
    ) -> bool:
        """
        Send message from one user to another.

        Args:
            from_user_id: Sender user ID
            to_user_id: Recipient user ID
            content: Message content
            content_type: OpenIM content type (101=text, 102=image, etc.)

        Returns:
            True if sent successfully
        """
        try:
            token = await self.get_token(from_user_id)
            if not token:
                logger.error("Failed to get OpenIM token")
                return False

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_url}/msg/send_msg",
                    headers={"token": token},
                    json={
                        "sendID": from_user_id,
                        "recvID": to_user_id,
                        "senderPlatformID": self.platform_id,
                        "contentType": content_type,
                        "content": {
                            "content": content
                        }
                    },
                    timeout=10.0
                )

                if response.status_code == 200:
                    logger.info(f"Message sent from {from_user_id} to {to_user_id}")
                    return True
                else:
                    logger.error(f"Failed to send message: {response.text}")
                    return False

        except Exception as e:
            logger.error(f"Error sending OpenIM message: {e}")
            return False

    async def send_batch_messages(
        self,
        from_user_id: str,
        to_user_ids: List[str],
        content: str,
        content_type: int = 101
    ) -> Dict[str, bool]:
        """
        Send same message to multiple users.

        Args:
            from_user_id: Sender user ID
            to_user_ids: List of recipient user IDs
            content: Message content
            content_type: OpenIM content type

        Returns:
            Dict mapping user_id to success status
        """
        results = {}
        for user_id in to_user_ids:
            success = await self.send_message(
                from_user_id=from_user_id,
                to_user_id=user_id,
                content=content,
                content_type=content_type
            )
            results[user_id] = success

        success_count = sum(1 for v in results.values() if v)
        logger.info(
            f"Batch message sent: {success_count}/{len(to_user_ids)} successful"
        )
        return results

    async def get_conversation_messages(
        self,
        user_id: str,
        conversation_id: str,
        offset: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get messages from a conversation.

        Args:
            user_id: User ID requesting messages
            conversation_id: Conversation ID (format: "single_{user1}_{user2}")
            offset: Message offset
            limit: Max number of messages

        Returns:
            List of message dictionaries
        """
        try:
            token = await self.get_token(user_id)
            if not token:
                return []

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_url}/msg/get_conversation_msg",
                    headers={"token": token},
                    json={
                        "conversationID": conversation_id,
                        "offset": offset,
                        "count": limit
                    },
                    timeout=10.0
                )

                if response.status_code == 200:
                    data = response.json()
                    messages = data.get("data", {}).get("messages", [])
                    logger.info(
                        f"Fetched {len(messages)} messages from {conversation_id}"
                    )
                    return messages
                else:
                    logger.error(f"Failed to fetch messages: {response.text}")
                    return []

        except Exception as e:
            logger.error(f"Error fetching OpenIM messages: {e}")
            return []

    async def get_unread_count(
        self,
        user_id: str,
        conversation_id: str
    ) -> int:
        """
        Get unread message count for a conversation.

        Args:
            user_id: User ID
            conversation_id: Conversation ID

        Returns:
            Unread message count
        """
        try:
            token = await self.get_token(user_id)
            if not token:
                return 0

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_url}/conversation/get_conversation",
                    headers={"token": token},
                    json={
                        "conversationID": conversation_id,
                        "ownerUserID": user_id
                    },
                    timeout=10.0
                )

                if response.status_code == 200:
                    data = response.json()
                    conversation = data.get("data", {}).get("conversation", {})
                    return conversation.get("unreadCount", 0)

        except Exception as e:
            logger.error(f"Error getting unread count: {e}")

        return 0

    async def mark_as_read(
        self,
        user_id: str,
        conversation_id: str,
        msg_ids: List[str]
    ) -> bool:
        """
        Mark messages as read.

        Args:
            user_id: User ID
            conversation_id: Conversation ID
            msg_ids: List of message IDs to mark as read

        Returns:
            True if successful
        """
        try:
            token = await self.get_token(user_id)
            if not token:
                return False

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_url}/msg/mark_msgs_as_read",
                    headers={"token": token},
                    json={
                        "conversationID": conversation_id,
                        "msgIDs": msg_ids
                    },
                    timeout=10.0
                )

                if response.status_code == 200:
                    logger.info(
                        f"Marked {len(msg_ids)} messages as read in {conversation_id}"
                    )
                    return True
                else:
                    logger.error(f"Failed to mark as read: {response.text}")
                    return False

        except Exception as e:
            logger.error(f"Error marking messages as read: {e}")
            return False

    async def create_single_conversation(
        self,
        user_id_1: str,
        user_id_2: str
    ) -> Optional[str]:
        """
        Create or get single conversation between two users.

        Args:
            user_id_1: First user ID
            user_id_2: Second user ID

        Returns:
            Conversation ID if successful
        """
        # OpenIM conversation ID format for single chat
        conversation_id = f"single_{user_id_1}_{user_id_2}"

        try:
            token = await self.get_token(user_id_1)
            if not token:
                return None

            # In OpenIM, single conversations are created automatically
            # when first message is sent
            logger.info(f"Conversation ID: {conversation_id}")
            return conversation_id

        except Exception as e:
            logger.error(f"Error creating conversation: {e}")
            return None

    def get_conversation_id(self, user_id_1: str, user_id_2: str) -> str:
        """
        Get conversation ID for single chat between two users.

        Args:
            user_id_1: First user ID (usually operator)
            user_id_2: Second user ID (usually app user)

        Returns:
            Conversation ID in OpenIM format
        """
        # OpenIM uses sorted user IDs for single chat
        users = sorted([user_id_1, user_id_2])
        return f"single_{users[0]}_{users[1]}"


# Global instance
openim_service = OpenIMService()

"""WebSocket manager for real-time communication."""
from typing import Dict, Set
from fastapi import WebSocket
import logging
import json

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Manage WebSocket connections for real-time support."""

    def __init__(self):
        # operator_id -> websocket
        self.active_connections: Dict[int, WebSocket] = {}
        # operator_id -> set of conversation_ids
        self.subscriptions: Dict[int, Set[str]] = {}

    async def connect(self, websocket: WebSocket, operator_id: int):
        """Connect operator websocket."""
        await websocket.accept()
        self.active_connections[operator_id] = websocket
        self.subscriptions[operator_id] = set()
        logger.info(f"Operator {operator_id} connected")

    async def disconnect(self, operator_id: int):
        """Disconnect operator websocket."""
        if operator_id in self.active_connections:
            del self.active_connections[operator_id]
        if operator_id in self.subscriptions:
            del self.subscriptions[operator_id]
        logger.info(f"Operator {operator_id} disconnected")

    async def subscribe(self, operator_id: int, conversation_id: str):
        """Subscribe operator to conversation updates."""
        if operator_id in self.subscriptions:
            self.subscriptions[operator_id].add(conversation_id)
            logger.info(f"Operator {operator_id} subscribed to {conversation_id}")

    async def unsubscribe(self, operator_id: int, conversation_id: str):
        """Unsubscribe operator from conversation updates."""
        if operator_id in self.subscriptions and conversation_id in self.subscriptions[operator_id]:
            self.subscriptions[operator_id].remove(conversation_id)
            logger.info(f"Operator {operator_id} unsubscribed from {conversation_id}")

    async def send_personal_message(self, operator_id: int, message: dict):
        """Send message to specific operator."""
        if operator_id in self.active_connections:
            websocket = self.active_connections[operator_id]
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"Error sending message to operator {operator_id}: {e}")
                await self.disconnect(operator_id)

    async def broadcast_message(self, conversation_id: str, message: dict):
        """Broadcast message to all operators subscribed to a conversation."""
        for operator_id, conversations in self.subscriptions.items():
            if conversation_id in conversations:
                await self.send_personal_message(operator_id, message)

    async def broadcast_to_all(self, message: dict):
        """Broadcast message to all connected operators."""
        disconnected = []
        for operator_id, websocket in self.active_connections.items():
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to operator {operator_id}: {e}")
                disconnected.append(operator_id)

        # Clean up disconnected clients
        for operator_id in disconnected:
            await self.disconnect(operator_id)

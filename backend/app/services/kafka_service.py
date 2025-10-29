"""Kafka service for consuming and producing Meme creation events."""
import json
import logging
from typing import Optional, Dict, Any, List
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.errors import KafkaError
from app.config import settings

logger = logging.getLogger(__name__)


class KafkaService:
    """Kafka service for Meme review."""

    def __init__(self):
        self.bootstrap_servers = settings.KAFKA_BOOTSTRAP_SERVERS
        self.consumer: Optional[AIOKafkaConsumer] = None
        self.producer: Optional[AIOKafkaProducer] = None
        self.pending_messages: List[Dict[str, Any]] = []  # In-memory storage for pending reviews

    async def start_consumer(self):
        """Start Kafka consumer for meme creation topic."""
        try:
            self.consumer = AIOKafkaConsumer(
                settings.KAFKA_MEME_CREATION_TOPIC,
                bootstrap_servers=self.bootstrap_servers,
                group_id=settings.KAFKA_CONSUMER_GROUP,
                auto_offset_reset=settings.KAFKA_AUTO_OFFSET_RESET,
                enable_auto_commit=False,  # Manual commit after processing
                value_deserializer=lambda m: json.loads(m.decode('utf-8'))
            )
            await self.consumer.start()
            logger.info(f"Kafka consumer started for topic: {settings.KAFKA_MEME_CREATION_TOPIC}")
        except Exception as e:
            logger.error(f"Failed to start Kafka consumer: {e}")
            raise

    async def start_producer(self):
        """Start Kafka producer for approved memes."""
        try:
            self.producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode('utf-8')
            )
            await self.producer.start()
            logger.info(f"Kafka producer started")
        except Exception as e:
            logger.error(f"Failed to start Kafka producer: {e}")
            raise

    async def stop_consumer(self):
        """Stop Kafka consumer."""
        if self.consumer:
            await self.consumer.stop()
            logger.info("Kafka consumer stopped")

    async def stop_producer(self):
        """Stop Kafka producer."""
        if self.producer:
            await self.producer.stop()
            logger.info("Kafka producer stopped")

    async def consume_messages(self, batch_size: int = 100):
        """
        Consume messages from Kafka and store in memory for review.
        This should be called periodically by a background task.
        """
        if not self.consumer:
            raise RuntimeError("Consumer not started")

        try:
            # Fetch messages in batch
            msg_batch = await self.consumer.getmany(timeout_ms=1000, max_records=batch_size)

            for topic_partition, messages in msg_batch.items():
                for message in messages:
                    # Add message to pending list with metadata
                    meme_data = message.value
                    meme_data['_kafka_offset'] = message.offset
                    meme_data['_kafka_partition'] = message.partition
                    meme_data['_kafka_timestamp'] = message.timestamp

                    # Check if already exists
                    if not any(m.get('order_id') == meme_data.get('order_id') for m in self.pending_messages):
                        self.pending_messages.append(meme_data)
                        logger.info(f"Added meme to review queue: order_id={meme_data.get('order_id')}")

            # Commit offsets after storing messages
            if msg_batch:
                await self.consumer.commit()

        except KafkaError as e:
            logger.error(f"Kafka error while consuming: {e}")
        except Exception as e:
            logger.error(f"Error consuming messages: {e}")

    async def produce_approved_meme(self, meme_data: Dict[str, Any]):
        """
        Produce approved meme message to approved topic.

        Args:
            meme_data: The meme data to send to approved topic
        """
        if not self.producer:
            raise RuntimeError("Producer not started")

        try:
            # Remove kafka metadata before sending
            clean_data = {k: v for k, v in meme_data.items() if not k.startswith('_kafka')}

            await self.producer.send(
                settings.KAFKA_MEME_APPROVED_TOPIC,
                value=clean_data
            )
            await self.producer.flush()
            logger.info(f"Sent approved meme to topic: order_id={clean_data.get('order_id')}")

        except Exception as e:
            logger.error(f"Failed to produce approved meme: {e}")
            raise

    def get_pending_memes(
        self,
        offset: int = 0,
        limit: int = 10,
        user_id: Optional[str] = None,
        symbol: Optional[str] = None,
        name: Optional[str] = None
    ) -> tuple[List[Dict[str, Any]], int]:
        """
        Get pending memes from in-memory storage with pagination and filtering.

        Returns:
            Tuple of (filtered_memes, total_count)
        """
        # Apply filters
        filtered = self.pending_messages

        if user_id:
            filtered = [m for m in filtered if user_id.lower() in m.get('user_id', '').lower()]

        if symbol:
            filtered = [m for m in filtered if symbol.lower() in m.get('symbol', '').lower()]

        if name:
            filtered = [m for m in filtered if name.lower() in m.get('name', '').lower()]

        total = len(filtered)

        # Apply pagination
        paginated = filtered[offset:offset + limit]

        return paginated, total

    def get_meme_by_order_id(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Get meme by order_id."""
        for meme in self.pending_messages:
            if meme.get('order_id') == order_id:
                return meme
        return None

    def remove_meme_by_order_id(self, order_id: str) -> bool:
        """
        Remove meme from pending list (after approve or reject).

        Returns:
            True if removed, False if not found
        """
        for i, meme in enumerate(self.pending_messages):
            if meme.get('order_id') == order_id:
                self.pending_messages.pop(i)
                logger.info(f"Removed meme from pending: order_id={order_id}")
                return True
        return False


# Global instance
kafka_service = KafkaService()

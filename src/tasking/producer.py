"""Kafka producer for async tasks."""
import json
import threading
from typing import Any, Dict, Optional

from kafka import KafkaProducer
from framework.commons.logger import logger
from src.config import Config
from src.core.correlation import get_correlation_id

_PRODUCER_LOCK = threading.Lock()
_PRODUCER: Optional[KafkaProducer] = None


def _get_producer() -> KafkaProducer:
    """Get or create the global Kafka producer instance."""
    global _PRODUCER
    if _PRODUCER is None:
        with _PRODUCER_LOCK:
            if _PRODUCER is None:
                logger.info("initializing kafka producer", extra={"servers": Config.KAFKA_BOOTSTRAP_SERVERS})
                _PRODUCER = KafkaProducer(
                    bootstrap_servers=Config.KAFKA_BOOTSTRAP_SERVERS.split(","),
                    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                    acks="all",
                    retries=5,
                )
    return _PRODUCER


def publish(task_name: str, payload: Dict[str, Any], topic: Optional[str] = None):
    """Publish a task to Kafka."""
    topic = topic or Config.KAFKA_TOPIC_FAST
    
    # Inject correlation ID for end-to-end tracing
    envelope = {
        "task": task_name,
        "payload": payload,
        "correlation_id": get_correlation_id(),
    }
    
    try:
        producer = _get_producer()
        future = producer.send(topic, envelope)
        
        # In DEV_MODE we might want to wait for the message to be sent
        if Config.DEV_MODE:
            future.get(timeout=10)
            
        logger.debug("task published", extra={"task_name": task_name, "topic": topic})
    except Exception as e:
        logger.error("failed to publish task", extra={"task_name": task_name, "topic": topic, "error": str(e)})
        # Depending on criticality, we might want to raise here
        # or rely on recovery.py for retry logic if we persisted it.
        raise

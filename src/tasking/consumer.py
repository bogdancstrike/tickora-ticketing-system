"""Kafka consumer for async tasks."""
import json
import time
from typing import List

from kafka import KafkaConsumer
from framework.commons.logger import logger
from framework.tracing import get_tracer

from src.config import Config
from src.core.correlation import set_correlation_id
from src.tasking.registry import get_handler

tracer = get_tracer("tickora.tasking")


def run_consumer(topics: List[str] = None):
    """Run the Kafka consumer loop."""
    if topics is None:
        topics = [Config.KAFKA_TOPIC_FAST, Config.KAFKA_TOPIC_SLOW]
        
    logger.info("starting kafka consumer", extra={"topics": topics, "group_id": Config.WORKER_NAME})
    
    consumer = KafkaConsumer(
        *topics,
        bootstrap_servers=Config.KAFKA_BOOTSTRAP_SERVERS.split(","),
        group_id=Config.WORKER_NAME,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        auto_offset_reset="earliest",
        enable_auto_commit=True,
    )
    
    try:
        for message in consumer:
            _process_message(message)
    except KeyboardInterrupt:
        logger.info("consumer shutting down")
    finally:
        consumer.close()


def _process_message(message):
    """Process a single Kafka message."""
    envelope = message.value
    task_name = envelope.get("task")
    payload = envelope.get("payload", {})
    correlation_id = envelope.get("correlation_id")
    
    set_correlation_id(correlation_id)
    
    with tracer.start_as_current_span(f"task.{task_name}") as span:
        span.set_attribute("task.name", task_name)
        span.set_attribute("kafka.topic", message.topic)
        span.set_attribute("kafka.offset", message.offset)
        
        try:
            handler = get_handler(task_name)
            logger.info("executing task", extra={"task_name": task_name, "topic": message.topic})
            
            start_time = time.time()
            handler(payload)
            duration = time.time() - start_time
            
            logger.info("task completed", extra={"task_name": task_name, "duration_ms": int(duration * 1000)})
        except Exception as e:
            logger.error("task failed", extra={"task_name": task_name, "error": str(e)})
            span.record_exception(e)
            # In a real system, we might want to push to a DLQ or retry

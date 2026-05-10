"""Kafka consumer for async tasks."""
import json
import time
from typing import List

from kafka import KafkaConsumer
from framework.commons.logger import logger
from framework.tracing import get_tracer

from src.config import Config
from src.common.correlation import set_correlation_id
from src.tasking.registry import get_handler


# Tracer is created lazily — `get_tracer` doesn't accept a name argument
# in this version of QF, and we don't want module-level surprises during
# import (e.g. when the consumer module is loaded from a unit test that
# doesn't actually run a Kafka loop).
def _tracer():
    return get_tracer()


def run_consumer(topics: List[str] = None):
    """Run the Kafka consumer loop.

    On startup we sweep `tasks` rows that were left as `running` by a
    crashed previous worker (heartbeat older than 10 minutes by default)
    and flip them back to `pending` so the next caller of `publish` for
    that name can retry. This is a safety net — proper retry/DLQ logic
    still belongs in handler-level code.
    """
    from src.tasking import lifecycle

    if topics is None:
        topics = [Config.KAFKA_TOPIC_FAST, Config.KAFKA_TOPIC_SLOW]

    recovered = lifecycle.recover_orphans()
    if recovered:
        logger.info("recovered stuck-running tasks", extra={"count": recovered})

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
    """Process a single Kafka message.

    The producer wrote a `pending` lifecycle row before sending; we flip
    it through `running` → `completed` / `failed`. The bookkeeping is
    failure-tolerant — a missing or out-of-band task_id (e.g. a message
    produced before the lifecycle table existed) just means we run the
    handler and skip the lifecycle bump.
    """
    from src.tasking import lifecycle

    envelope = message.value
    task_name = envelope.get("task")
    payload = envelope.get("payload", {})
    correlation_id = envelope.get("correlation_id")
    task_id = envelope.get("task_id")

    set_correlation_id(correlation_id)

    with _tracer().start_as_current_span(f"task.{task_name}") as span:
        span.set_attribute("task.name", task_name)
        span.set_attribute("kafka.topic", message.topic)
        span.set_attribute("kafka.offset", message.offset)
        if task_id:
            span.set_attribute("task.id", task_id)

        try:
            handler = get_handler(task_name)
            logger.info("executing task", extra={
                "task_name": task_name, "task_id": task_id, "topic": message.topic,
            })

            lifecycle.mark_running(task_id)
            start_time = time.time()
            handler(payload)
            duration = time.time() - start_time
            lifecycle.mark_completed(task_id)

            logger.info("task completed", extra={
                "task_name": task_name, "task_id": task_id, "duration_ms": int(duration * 1000),
            })
        except Exception as e:
            lifecycle.mark_failed(task_id, str(e))
            logger.error("task failed", extra={
                "task_name": task_name, "task_id": task_id, "error": str(e),
            })
            span.record_exception(e)
            # In a real system, we might want to push to a DLQ or retry

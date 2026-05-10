"""Kafka producer for async tasks."""
import json
import threading
from typing import Any, Dict, Optional

from kafka import KafkaProducer
from framework.commons.logger import logger
from src.config import Config
from src.core.correlation import get_correlation_id
from src.core.db import enqueue_after_commit

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
    """Publish a task.

    Two paths:
      * **inline (DEV)** — run the handler in-process after the current DB
        transaction commits. Mostly for local development; the lifecycle
        row is still written so `tasks` looks identical regardless of mode.
      * **kafka** — write the lifecycle row, then send the envelope. The
        `task_id` travels in the envelope so the consumer can look up and
        flip the same row.

    The lifecycle row is best-effort: if it fails to insert we still
    publish the message and the handler still runs. Operator visibility is
    nice-to-have but the system must keep working when the DB is degraded.
    """
    topic = topic or Config.KAFKA_TOPIC_FAST
    correlation_id = get_correlation_id()

    # Lifecycle: register a `pending` row, get back its id.
    from src.tasking import lifecycle
    task_id = lifecycle.create(
        task_name=task_name, payload=payload,
        correlation_id=correlation_id, topic=topic,
    )

    envelope = {
        "task": task_name,
        "task_id": task_id,
        "payload": payload,
        "correlation_id": correlation_id,
    }

    if Config.INLINE_TASKS_IN_DEV:
        def run_inline() -> None:
            from src.tasking.registry import get_handler
            try:
                _ensure_local_handlers_registered()
                lifecycle.mark_running(task_id)
                logger.info("executing task inline", extra={
                    "task_name": task_name, "task_id": task_id,
                })
                get_handler(task_name)(payload)
                lifecycle.mark_completed(task_id)
            except Exception as exc:
                lifecycle.mark_failed(task_id, str(exc))
                logger.error("inline task failed", extra={
                    "task_name": task_name, "task_id": task_id, "error": str(exc),
                })

        enqueue_after_commit(run_inline)
        logger.debug("task queued for inline execution", extra={"task_name": task_name, "task_id": task_id})
        return task_id

    try:
        producer = _get_producer()
        future = producer.send(topic, envelope)

        # In DEV_MODE we might want to wait for the message to be sent
        if Config.DEV_MODE:
            future.get(timeout=10)

        logger.debug("task published", extra={"task_name": task_name, "task_id": task_id, "topic": topic})
        return task_id
    except Exception as e:
        # Couldn't ship the message — flip the row to failed so it doesn't
        # sit at `pending` forever, then propagate.
        lifecycle.mark_failed(task_id, f"publish_failed: {e}")
        logger.error("failed to publish task", extra={
            "task_name": task_name, "task_id": task_id, "topic": topic, "error": str(e),
        })
        raise


def _ensure_local_handlers_registered() -> None:
    # Import task modules for API/dev inline execution. The worker does this at
    # process startup; API-only dev runs need the same registration before a
    # queued task can be executed without Kafka.
    import src.ticketing.notifications  # noqa: F401

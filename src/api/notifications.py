"""Notification and SSE endpoints."""
import json
from datetime import datetime, timezone

from flask import Response, stream_with_context
from sqlalchemy import desc, select, update

from framework.commons.logger import logger
from src.core.db import get_db
from src.core.redis_client import get_redis
from src.iam.decorators import require_authenticated
from src.iam.principal import Principal
from src.ticketing.models import Notification


def _serialize(n: Notification) -> dict:
    return {
        "id":         n.id,
        "type":       n.type,
        "title":      n.title,
        "body":       n.body,
        "ticket_id":  n.ticket_id,
        "read":       bool(n.is_read),
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }


@require_authenticated
def list_notifications(app, operation, request, *, principal: Principal, **kwargs):
    """Most recent notifications for the current user."""
    with get_db() as db:
        rows = list(db.scalars(
            select(Notification)
            .where(Notification.user_id == principal.user_id)
            .order_by(desc(Notification.created_at))
            .limit(50)
        ))
        return ({"items": [_serialize(n) for n in rows]}, 200)


@require_authenticated
def mark_notifications_read(app, operation, request, *, principal: Principal, **kwargs):
    """Bulk mark all unread notifications for the current user as read."""
    with get_db() as db:
        db.execute(
            update(Notification)
            .where(Notification.user_id == principal.user_id, Notification.is_read.is_(False))
            .values(is_read=True, read_at=datetime.now(timezone.utc))
        )
        return ({"ok": True}, 200)

@require_authenticated
def stream(app, operation, request, *, principal: Principal, **kwargs):
    """SSE stream for real-time notifications."""
    user_id = principal.user_id
    
    def event_stream():
        redis = get_redis()
        pubsub = redis.pubsub()
        channel = f"notifications:{user_id}"
        pubsub.subscribe(channel)
        
        logger.info("sse stream started", extra={"user_id": user_id})
        
        # Send initial heartbeat or connection confirmation
        yield f"data: {json.dumps({'type': 'connection', 'status': 'connected'})}\n\n"
        
        try:
            while True:
                message = pubsub.get_message(ignore_subscribe_messages=True, timeout=30.0)
                if message:
                    data = message['data']
                    if isinstance(data, bytes):
                        data = data.decode('utf-8')
                    yield f"data: {data}\n\n"
                else:
                    # Heartbeat to keep connection alive
                    yield ": heartbeat\n\n"
        except Exception as e:
            logger.error("sse stream error", extra={"user_id": user_id, "error": str(e)})
        finally:
            pubsub.unsubscribe(channel)
            logger.info("sse stream closed", extra={"user_id": user_id})

    return Response(
        stream_with_context(event_stream()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable buffering for Nginx
        }
    )

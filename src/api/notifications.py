"""Notification and SSE endpoints."""
import json
import uuid
from datetime import datetime, timezone

from flask import Response, stream_with_context
from sqlalchemy import desc, select, update
from flask import request as flask_request

from framework.commons.logger import logger
from src.common.db import get_db
from src.common.redis_client import get_redis
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
def mark_notification_read(app, operation, request, *, principal: Principal, **kwargs):
    """Mark one notification for the current user as read."""
    notification_id = kwargs.get("notification_id") or flask_request.view_args.get("notification_id")
    with get_db() as db:
        db.execute(
            update(Notification)
            .where(
                Notification.id == notification_id,
                Notification.user_id == principal.user_id,
                Notification.is_read.is_(False),
            )
            .values(is_read=True, read_at=datetime.now(timezone.utc))
        )
        return ({"ok": True}, 200)


@require_authenticated
def create_stream_ticket(app, operation, request, *, principal: Principal, **kwargs):
    """Generate a short-lived ticket to authenticate the SSE stream without
    putting the JWT in the URL.
    """
    # Extract token from Authorization header
    auth = flask_request.headers.get("Authorization") or ""
    if not auth.lower().startswith("bearer "):
        return ({"error": "missing token"}, 401)

    token = auth.split(" ", 1)[1].strip()
    ticket = str(uuid.uuid4())

    redis = get_redis()
    if not redis:
        return ({"error": "redis unavailable"}, 503)

    # Store the token with a short TTL (30s)
    redis.set(f"sse_ticket:{ticket}", token, ex=30)

    return ({"ticket": ticket}, 200)


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

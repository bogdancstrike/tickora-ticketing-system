"""Notification and SSE endpoints."""
import json
import time
from flask import Response, stream_with_context

from framework.commons.logger import logger
from src.core.redis_client import get_redis
from src.iam.decorators import require_authenticated
from src.iam.principal import Principal

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

"""Lazy-initialized Redis client. Returns None if Redis is unreachable."""
from typing import Optional

import redis

from src.config import Config
from framework.commons.logger import logger as log

_client: Optional[redis.Redis] = None


def get_redis() -> Optional[redis.Redis]:
    global _client
    if _client is not None:
        return _client
    try:
        _client = redis.from_url(Config.REDIS_URL, decode_responses=True, socket_timeout=2.0)
        _client.ping()
    except Exception as e:
        log.warning("redis unavailable", extra={"error": str(e)})
        _client = None
    return _client

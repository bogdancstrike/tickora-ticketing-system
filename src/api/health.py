"""Health, liveness, readiness endpoints. QF handler signature."""
from sqlalchemy import text

from src.core.db import get_engine
from src.core.redis_client import get_redis
from src.core.spans import set_attr, span
from framework.commons.logger import logger as log


def _ok(checks: dict) -> tuple[dict, int]:
    return ({"status": "ok", "checks": checks}, 200)


def _degraded(checks: dict) -> tuple[dict, int]:
    return ({"status": "degraded", "checks": checks}, 503)


def liveness(app, operation, request, **kwargs):
    """Process is up. Used by k8s livenessProbe."""
    with span("api.liveness") as current:
        set_attr(current, "health.ok", True)
        return ({"status": "ok"}, 200)


def readiness(app, operation, request, **kwargs):
    """Process can serve. DB + Redis reachable."""
    with span("api.readiness") as current:
        checks = {}
        try:
            with get_engine().connect() as conn:
                conn.execute(text("SELECT 1"))
            checks["postgres"] = "ok"
        except Exception as e:
            checks["postgres"] = f"fail: {e}"

        r = get_redis()
        if r is not None:
            try:
                r.ping()
                checks["redis"] = "ok"
            except Exception as e:
                checks["redis"] = f"fail: {e}"
        else:
            checks["redis"] = "fail: unreachable"

        ok = all(v == "ok" for v in checks.values())
        set_attr(current, "health.ok", ok)
        set_attr(current, "health.postgres", checks.get("postgres"))
        set_attr(current, "health.redis", checks.get("redis"))
        if ok:
            return _ok(checks)
        return _degraded(checks)


def health_check(app, operation, request, **kwargs):
    """Detailed health probe."""
    with span("api.health_check"):
        return readiness(app, operation, request, **kwargs)

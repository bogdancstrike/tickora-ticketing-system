"""Per-request correlation ID + principal context, propagated via contextvars."""
import contextvars
import uuid
from typing import Optional

_correlation_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "correlation_id", default=None
)
_user_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "user_id", default=None
)
_ticket_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "ticket_id", default=None
)


def new_correlation_id() -> str:
    return str(uuid.uuid4())


def set_correlation_id(value: Optional[str]) -> None:
    _correlation_id.set(value)


def get_correlation_id() -> Optional[str]:
    return _correlation_id.get()


def set_user_id(value: Optional[str]) -> None:
    _user_id.set(value)


def get_user_id() -> Optional[str]:
    return _user_id.get()


def set_ticket_id(value: Optional[str]) -> None:
    _ticket_id.set(value)


def get_ticket_id() -> Optional[str]:
    return _ticket_id.get()


def clear() -> None:
    set_correlation_id(None)
    set_user_id(None)
    set_ticket_id(None)


def install_flask_hooks(app) -> None:
    """Wire before_request/after_request hooks on a Flask app."""
    from flask import g, make_response, request

    from src.config import Config

    def _allowed_origin() -> str | None:
        origin = request.headers.get("Origin")
        if not origin:
            return None
        if "*" in Config.ALLOWED_ORIGINS or origin in Config.ALLOWED_ORIGINS:
            return origin
        return None

    def _add_cors_headers(response):
        origin = _allowed_origin()
        if origin:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Headers"] = (
                "Authorization, Content-Type, X-Correlation-Id"
            )
            response.headers["Access-Control-Allow-Methods"] = (
                "GET, POST, PUT, PATCH, DELETE, OPTIONS"
            )
            response.headers["Access-Control-Max-Age"] = "600"
        return response

    @app.before_request
    def _before():
        cid = request.headers.get("X-Correlation-Id") or new_correlation_id()
        set_correlation_id(cid)
        g.correlation_id = cid
        if request.method == "OPTIONS":
            return _add_cors_headers(make_response(("", 204)))

    @app.after_request
    def _after(response):
        cid = get_correlation_id()
        if cid:
            response.headers["X-Correlation-Id"] = cid
        return _add_cors_headers(response)

    @app.teardown_request
    def _teardown(_exc):
        clear()

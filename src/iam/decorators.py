"""Auth decorators wrapping QF handler functions.

Handlers have signature `handler(app, operation, request, **kwargs)`. Decorated
versions extract+verify the bearer token, hydrate a Principal, and inject it
into kwargs as `principal=<Principal>`.
"""
from functools import wraps
from typing import Callable, Iterable

from flask import request as flask_request

from src.common.correlation import set_user_id
from src.common.errors import AuthenticationError, PermissionDeniedError, TickoraError
from src.common.spans import set_attr, span
from src.iam.principal import Principal
from src.iam.service import principal_from_claims
from src.iam.token_verifier import verify_token
from framework.commons.logger import logger as log


def _extract_bearer() -> str:
    auth = flask_request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()

    # Fallback to query parameter for EventSource (SSE) support.
    # Uses a short-lived one-time ticket from Redis.
    ticket = flask_request.args.get("sse_ticket")
    if ticket:
        if not flask_request.path.rstrip("/").endswith("/api/notifications/stream"):
            raise AuthenticationError("sse_ticket is only valid for notification streams")
        from src.common.redis_client import get_redis
        redis = get_redis()
        if redis:
            token = redis.get(f"sse_ticket:{ticket}")
            if token:
                redis.delete(f"sse_ticket:{ticket}")  # One-time use
                return token

    raise AuthenticationError("missing bearer token")


def _build_principal() -> Principal:
    """Verify the bearer token and produce the request-scoped Principal.

    Side effect: refreshes the user's presence key in Redis so the admin
    overview can show how many users are currently logged in.
    """
    with span("iam.build_principal") as current:
        token = _extract_bearer()
        claims = verify_token(token)
        principal = principal_from_claims(claims)
        set_user_id(principal.user_id)
        # Presence ping — failure-tolerant, fire-and-forget.
        try:
            from src.common.session_tracker import mark_active
            mark_active(principal.user_id)
        except Exception:
            pass
        set_attr(current, "iam.user_id", principal.user_id)
        set_attr(current, "iam.username", principal.username)
        set_attr(current, "iam.user_type", principal.user_type)
        set_attr(current, "iam.roles", ",".join(sorted(principal.global_roles)))
        return principal


def _err_response(err: TickoraError):
    """Convert a domain error to a (body, status) tuple.

    flask_restx overrides Flask's errorhandler, so we must return raw dicts
    (not Flask Response objects) — flask_restx serializes the body itself.
    """
    return (err.to_dict(), err.status_code)


def require_authenticated(fn: Callable) -> Callable:
    @wraps(fn)
    def wrapper(app, operation, request, **kwargs):
        with span(f"api.{fn.__name__}") as current:
            try:
                principal = _build_principal()
                kwargs["principal"] = principal
                set_attr(current, "iam.user_id", principal.user_id)
                set_attr(current, "iam.username", principal.username)
                result = fn(app, operation, request, **kwargs)
                if isinstance(result, tuple) and len(result) > 1:
                    set_attr(current, "http.status_code", result[1])
                return result
            except TickoraError as e:
                set_attr(current, "error.type", e.code)
                set_attr(current, "http.status_code", e.status_code)
                if e.status_code >= 500:
                    log.exception("unhandled domain error", extra={"error": str(e)})
                return _err_response(e)
    return wrapper


def require_role(*roles: str) -> Callable[[Callable], Callable]:
    def deco(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(app, operation, request, **kwargs):
            with span(f"api.{fn.__name__}.require_role", required_roles=",".join(roles)) as current:
                try:
                    principal: Principal = kwargs.get("principal") or _build_principal()
                    set_attr(current, "iam.user_id", principal.user_id)
                    set_attr(current, "iam.username", principal.username)
                    if not principal.has_any(roles):
                        log.info("access_denied: role", extra={
                            "user_id": principal.user_id, "needed": list(roles),
                        })
                        raise PermissionDeniedError(
                            f"requires one of: {', '.join(roles)}",
                            details={"required_roles": list(roles)},
                        )
                    kwargs["principal"] = principal
                    return fn(app, operation, request, **kwargs)
                except TickoraError as e:
                    set_attr(current, "error.type", e.code)
                    set_attr(current, "http.status_code", e.status_code)
                    if e.status_code >= 500:
                        log.exception("unhandled domain error", extra={"error": str(e)})
                    return _err_response(e)
        return wrapper
    return deco


def require_any(roles: Iterable[str]) -> Callable[[Callable], Callable]:
    return require_role(*roles)

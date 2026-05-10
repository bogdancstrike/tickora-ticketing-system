"""Domain exception hierarchy and Flask error mapping."""
from typing import Any, Optional


class TickoraError(Exception):
    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str = "", *, details: Optional[dict[str, Any]] = None):
        super().__init__(message or self.code)
        self.message = message or self.code
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        out = {"error": self.code, "message": self.message}
        if self.details:
            out["details"] = self.details
        return out


class ValidationError(TickoraError):
    status_code = 422
    code = "validation_error"


class AuthenticationError(TickoraError):
    status_code = 401
    code = "authentication_required"


class PermissionDeniedError(TickoraError):
    status_code = 403
    code = "permission_denied"


class NotFoundError(TickoraError):
    status_code = 404
    code = "not_found"


class ConcurrencyConflictError(TickoraError):
    status_code = 409
    code = "concurrency_conflict"


class BusinessRuleError(TickoraError):
    status_code = 422
    code = "business_rule_violation"


class RateLimitError(TickoraError):
    status_code = 429
    code = "rate_limited"


def install_flask_error_handlers(app) -> None:
    from flask import jsonify

    @app.errorhandler(TickoraError)
    def _handle(err: TickoraError):
        resp = jsonify(err.to_dict())
        resp.status_code = err.status_code
        return resp

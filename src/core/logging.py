"""Structured JSON logger with contextvar-injected fields."""
import json
import logging
import sys
from datetime import datetime, timezone

from src.config import Config
from src.core.correlation import get_correlation_id, get_ticket_id, get_user_id


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts":      datetime.now(timezone.utc).isoformat(),
            "level":   record.levelname,
            "service": Config.SERVICE_NAME,
            "logger":  record.name,
            "msg":     record.getMessage(),
        }
        cid = get_correlation_id()
        uid = get_user_id()
        tid = get_ticket_id()
        if cid: payload["correlation_id"] = cid
        if uid: payload["user_id"]        = uid
        if tid: payload["ticket_id"]      = tid

        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)

        # Allow extra={"k": "v"} on log calls
        for k, v in record.__dict__.items():
            if k in ("args", "msg", "levelname", "levelno", "pathname", "filename",
                     "module", "exc_info", "exc_text", "stack_info", "lineno",
                     "funcName", "created", "msecs", "relativeCreated", "thread",
                     "threadName", "processName", "process", "name", "message",
                     "taskName"):
                continue
            try:
                json.dumps(v)
                payload[k] = v
            except (TypeError, ValueError):
                payload[k] = repr(v)

        return json.dumps(payload, ensure_ascii=False)


_configured = False


def configure() -> None:
    global _configured
    if _configured:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, Config.LOG_LEVEL.upper(), logging.INFO))
    # Quiet libraries that flood DEBUG
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    logging.getLogger("kafka").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    _configured = True


def get_logger(name: str = "tickora") -> logging.Logger:
    configure()
    return logging.getLogger(name)

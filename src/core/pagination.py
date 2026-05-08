"""Cursor pagination helpers — opaque base64 cursor over (sort_value, id)."""
import base64
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional


@dataclass
class Cursor:
    sort_value: Any
    id: str

    def encode(self) -> str:
        v = self.sort_value
        if isinstance(v, datetime):
            v = v.isoformat()
        raw = json.dumps([v, self.id], separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    @staticmethod
    def decode(token: Optional[str]) -> Optional["Cursor"]:
        if not token:
            return None
        pad = "=" * (-len(token) % 4)
        try:
            raw = base64.urlsafe_b64decode(token + pad)
            v, i = json.loads(raw)
        except Exception:
            return None
        if isinstance(v, str):
            try:
                v = datetime.fromisoformat(v)
            except ValueError:
                pass
        return Cursor(sort_value=v, id=i)


def clamp_limit(limit: Optional[int], *, default: int = 50, max_: int = 200) -> int:
    if limit is None:
        return default
    try:
        n = int(limit)
    except (TypeError, ValueError):
        return default
    return max(1, min(n, max_))

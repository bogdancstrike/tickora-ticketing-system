"""Back-compat shim — moved to `src.common.rate_limiter`."""
from src.common.rate_limiter import _KEY_PREFIX, check  # noqa: F401
# Tests monkeypatch `get_redis` on this module, so re-export it too.
from src.common.rate_limiter import get_redis  # noqa: F401

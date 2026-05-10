"""Back-compat shim — moved to `src.common.session_tracker`."""
from src.common.session_tracker import (  # noqa: F401
    active_user_count,
    active_user_ids,
    mark_active,
)

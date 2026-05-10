"""Back-compat shim — moved to `src.common.cache`.

This re-export keeps existing `from src.core.cache import …` imports
working after the 2026-05-10 module split. New code should import from
`src.common.cache` directly.
"""
from src.common.cache import *  # noqa: F401,F403
from src.common.cache import (  # noqa: F401  re-export private helper used in tests
    _json_default,
)

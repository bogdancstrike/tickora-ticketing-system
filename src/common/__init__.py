"""Cross-module utilities — pagination, caching, rate-limiting, presence,
object storage, request metadata, span helpers.

These don't belong in `src/core/` because they're not infrastructure the
framework boot depends on. They're reusable building blocks any module
can pick up. `src/core/` keeps the smallest set: db engine + Base, error
hierarchy, correlation context, JWKS-aware tracing.

Migration path: the old `src/core/*` paths still resolve via thin
re-export shims so existing imports keep working. New code should import
from `src.common.<name>` directly.
"""

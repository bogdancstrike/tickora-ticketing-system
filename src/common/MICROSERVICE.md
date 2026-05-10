# `common/` as a standalone package

`common/` is a pure utility library. It has no domain logic, no API
surface, no DB tables of its own. It exists to be reusable.

## Dependency boundary

`common/` imports only:

| Symbol                     | Source              | Required? |
|----------------------------|---------------------|-----------|
| `Config`                   | `src.config`        | Yes — used by `rate_limiter` (limit-per-window), `request_metadata` (TRUSTED_PROXIES). |
| `RateLimitError`           | `src.core.errors`   | Yes — `rate_limiter.check` raises it. |
| `get_redis()`              | `src.core.redis_client` | Yes — `cache`, `rate_limiter`, `session_tracker`. |
| `get_tracer()`             | `src.core.tracing`  | Yes — `spans`. |

Nothing else. Specifically: **no imports from** `iam`, `audit`,
`ticketing`, `tasking`. ✅

## Extraction recipe

Copy these files into the new project (preserving paths under `src/`):

```
src/
├── config.py                     # bring or replace with your own
├── core/
│   ├── __init__.py
│   ├── errors.py                 # RateLimitError + the rest of the hierarchy
│   ├── redis_client.py
│   └── tracing.py
└── common/
    ├── __init__.py
    ├── cache.py
    ├── object_storage.py
    ├── pagination.py
    ├── rate_limiter.py
    ├── request_metadata.py
    ├── session_tracker.py
    └── spans.py
```

Plus your `pyproject.toml` / `requirements.txt` entries:

* `redis>=5.0.0`
* `boto3>=1.34.0`               (only if you use `object_storage`)
* `flask>=3.0.0`                (only if you use `request_metadata`)
* `opentelemetry-api>=1.25.0`   (only if you use `spans`)

## Wiring

```python
from src.common import cache, rate_limiter, session_tracker
# Just import and call. Every helper fails open when Redis is missing.
```

No registration, no boot-time setup. Drop in and go.

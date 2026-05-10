# `common/` as a standalone package

`common/` is the shared platform package. It has no domain logic or API
surface of its own, but it owns the infrastructure primitives every
extracted service needs: DB session/base, errors, correlation, Redis,
tracing, pagination, caching, request metadata, rate limiting, and object
storage.

## Dependency boundary

`common/` imports only:

| Symbol                     | Source              | Required? |
|----------------------------|---------------------|-----------|
| `Config`                   | `src.config`        | Yes — env-driven settings. |
| SQLAlchemy                 | external dependency | Yes if the service uses `common.db`. |
| Redis                      | external dependency | Optional; helpers fail open when unavailable. |
| Flask                      | external dependency | Optional; only for request metadata and error handlers. |
| QF framework logger/tracing | external dependency | Optional; tracing falls back to no-op. |

Nothing else. Specifically: **no imports from** `iam`, `audit`,
`ticketing`, `tasking`. ✅

## Extraction recipe

Copy these files into the new project (preserving paths under `src/`):

```
src/
├── config.py                     # bring or replace with your own
└── common/
    ├── __init__.py
    ├── cache.py
    ├── correlation.py
    ├── db.py
    ├── errors.py
    ├── object_storage.py
    ├── pagination.py
    ├── rate_limiter.py
    ├── redis_client.py
    ├── request_metadata.py
    ├── session_tracker.py
    ├── spans.py
    └── tracing.py
```

Plus your `pyproject.toml` / `requirements.txt` entries:

* `redis>=5.0.0`
* `sqlalchemy`, `psycopg2-binary`  (if you use `common.db`)
* `boto3>=1.34.0`               (only if you use `object_storage`)
* `flask>=3.0.0`                (only if you use `request_metadata`)
* `opentelemetry-api>=1.25.0`   (only if you use `spans`)

## Wiring

```python
from src.common import cache, rate_limiter, session_tracker
# Just import and call. Every helper fails open when Redis is missing.
```

No registration, no boot-time setup. Drop in and go.

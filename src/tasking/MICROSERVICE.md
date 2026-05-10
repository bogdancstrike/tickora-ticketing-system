# `tasking/` as a standalone microservice

`tasking/` is the async fanout layer. Extract it when you want a
generic background-job runner without dragging the rest of the modulith
along.

## Dependency boundary

`tasking/` imports only:

| Symbol                       | Source                | Required? |
|------------------------------|-----------------------|-----------|
| `Config`                     | `src.config`          | Yes — Kafka servers, topic names, `INLINE_TASKS_IN_DEV`, `TASK_HANDLER_MODULES`. |
| `Base`                       | `src.core.db`         | Yes — `Task` ORM. |
| `get_db`, `enqueue_after_commit` | `src.core.db`     | Yes — lifecycle row writes + DEV inline scheduling. |
| `get_correlation_id` / `set_correlation_id` | `src.core.correlation` | Yes — task envelopes carry the originating correlation id. |

Specifically: **no import from `ticketing`, `audit`, `iam`, or `common`.**
Handler modules (where `@register_task` is called) are listed in
`Config.TASK_HANDLER_MODULES` — tasking doesn't know or care which
package owns them.

## Extraction recipe

Copy these files into the new project:

```
src/
├── config.py                     # bring or replace
├── core/                         # required
│   ├── __init__.py
│   ├── correlation.py
│   ├── db.py
│   └── errors.py                 # for the API surface below
├── tasking/
│   ├── __init__.py
│   ├── consumer.py
│   ├── lifecycle.py
│   ├── models.py
│   ├── producer.py
│   └── registry.py
└── api/
    └── tasks.py                  # optional — admin GET /api/tasks
```

Plus the migration that owns the table:

* `e7b34cd9f211_tasks_lifecycle_table.py` — required. Creates `tasks`
  with status / payload / attempts / timestamps / heartbeat + 3 indexes.

Python deps:

* `kafka-python>=2.0.2`           (consumer + producer)
* `sqlalchemy`, `psycopg2-binary`, `alembic`

## Wiring

```python
# config (env or settings file)
TASK_HANDLER_MODULES = "myapp.notifications,myapp.exports,myapp.imports"
KAFKA_BOOTSTRAP_SERVERS = "kafka-1:9092,kafka-2:9092"
KAFKA_TOPIC_FAST = "tasks_fast"
KAFKA_TOPIC_SLOW = "tasks_slow"

# producers
from src.tasking.producer import publish
task_id = publish("send_email", {"to": "user@example.com", "subject": "hi"})

# consumer entry point (worker process)
from src.tasking.consumer import run_consumer
run_consumer()       # also calls lifecycle.recover_orphans() on startup

# admin queries
from src.tasking import lifecycle
with get_db() as db:
    failed = lifecycle.list_tasks(db, status="failed", limit=50)
```

The consumer doesn't import any handler at boot. The producer's
`_ensure_local_handlers_registered()` (used in DEV inline mode) loops
over `Config.TASK_HANDLER_MODULES` and imports each one — the side
effect of that import is what populates the registry.

## Lifecycle states

```
pending  →  running  →  completed
                    ↘  failed
```

* **pending**   — `producer.publish` wrote the row, no handler ran yet.
* **running**   — `consumer._process_message` (or DEV inline) flipped it.
                  `last_heartbeat_at` should be ticking via
                  `lifecycle.heartbeat(task_id)` for long jobs.
* **completed** — handler returned without raising.
* **failed**    — handler raised. `last_error` carries the exception
                  message (truncated to 4 KB).

`recover_orphans()` runs once at consumer startup and flips any rows
left at `running` past their heartbeat-staleness threshold (default 10
minutes) back to `pending`. Run again after an unclean shutdown.

## What a microservice does NOT need from the modulith

* `src.ticketing.*`              — handlers register themselves; tasking imports nothing about ticket logic.
* `src.audit.*`                  — task lifecycle is its own audit; if you want audit rows for tasks, add an `@register_task` wrapper that calls `audit.service.record`.
* `src.iam.*`                    — task execution is system-internal; no Principal involved.
* `src.common.*`                 — none required for the core lifecycle.

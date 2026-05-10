"""Tasking module — async fanout + persisted task lifecycle.

Owns:
  * `models.Task` — the `tasks` table (status, payload, attempts, timing).
  * `lifecycle.*` — `create / mark_running / mark_completed / mark_failed /
    heartbeat / recover_orphans / list_tasks / get_task`.
  * `producer.publish` — writes a `pending` row, then ships the envelope
    (Kafka or DEV inline). Returns the `task_id`.
  * `consumer.run_consumer` / `_process_message` — flips the row through
    the lifecycle around the registered handler call.
  * `registry.register_task(name)` — decorator for handler authors.

External dependencies (the modulith → microservice boundary):
  * `src.config`, `src.core.db`, `src.core.correlation`. Nothing else.
  * Handler modules are registered indirectly via
    `Config.TASK_HANDLER_MODULES` — tasking imports nothing about
    ticketing or any specific producer.

See `src/tasking/MICROSERVICE.md` for the extraction recipe.
"""

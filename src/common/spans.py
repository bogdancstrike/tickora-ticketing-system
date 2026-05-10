"""Small helpers for OpenTelemetry spans."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from src.common.tracing import get_tracer

_tracer = get_tracer()


@contextmanager
def span(name: str, **attrs) -> Iterator:
    with _tracer.start_as_current_span(name) as current:
        for key, value in attrs.items():
            set_attr(current, key, value)
        yield current


def set_attr(current, key: str, value) -> None:
    if value is None:
        return
    try:
        current.set_attribute(key, value)
    except Exception:
        pass

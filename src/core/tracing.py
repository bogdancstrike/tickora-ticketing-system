"""Tracing facade. Wraps QF's tracer when available, falls back to a no-op."""
try:
    from framework.tracing import get_tracer  # type: ignore
except ImportError:
    class _NoOpSpan:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def set_attribute(self, *a, **kw): pass
        def add_event(self, *a, **kw): pass
        def record_exception(self, *a, **kw): pass

    class _NoOpTracer:
        def start_as_current_span(self, _name, *_a, **_kw):
            return _NoOpSpan()

    def get_tracer():  # type: ignore
        return _NoOpTracer()

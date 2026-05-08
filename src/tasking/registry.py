"""Task registry for async processing."""
import functools
from typing import Any, Callable, Dict

from framework.commons.logger import logger

# Type alias for task handlers
TaskHandler = Callable[..., Any]

# Global task registry
_TASK_REGISTRY: Dict[str, TaskHandler] = {}


def register_task(name: str):
    """Decorator to register a task handler."""

    def decorator(func: TaskHandler):
        if name in _TASK_REGISTRY:
            raise ValueError(f"Task '{name}' is already registered")
        
        _TASK_REGISTRY[name] = func
        logger.debug("task registered", extra={"task_name": name})
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        
        return wrapper

    return decorator


def get_handler(name: str) -> TaskHandler:
    """Get the handler for a registered task."""
    if name not in _TASK_REGISTRY:
        raise ValueError(f"Task '{name}' is not registered")
    return _TASK_REGISTRY[name]


def list_tasks() -> Dict[str, TaskHandler]:
    """List all registered tasks."""
    return _TASK_REGISTRY.copy()

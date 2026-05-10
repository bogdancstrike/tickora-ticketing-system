"""SQLAlchemy engine, session factory, and request-scoped context manager."""
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from src.config import Config


class Base(DeclarativeBase):
    """Declarative base for all Tickora ORM models."""


_engine = create_engine(
    Config.DATABASE_URL,
    pool_size=Config.DB_POOL_SIZE,
    max_overflow=Config.DB_MAX_OVERFLOW,
    pool_timeout=Config.DB_POOL_TIMEOUT,
    pool_pre_ping=True,
    future=True,
)

_SessionFactory = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)
_CURRENT_SESSION: ContextVar[Session | None] = ContextVar("tickora_current_session", default=None)


def current_session() -> Session | None:
    return _CURRENT_SESSION.get()


def enqueue_after_commit(task) -> None:
    session = current_session()
    if session is None:
        task()
        return
    session.info.setdefault("after_commit_tasks", []).append(task)


@contextmanager
def get_db() -> Iterator[Session]:
    """Yield a Session, commit on success, rollback on error, always close."""
    session = _SessionFactory()
    token = _CURRENT_SESSION.set(session)
    try:
        yield session
        session.commit()
        tasks = list(session.info.pop("after_commit_tasks", []))
        for task in tasks:
            task()
    except Exception:
        session.rollback()
        raise
    finally:
        _CURRENT_SESSION.reset(token)
        session.close()


def get_engine():
    return _engine


def init_db() -> None:
    """Create tables for models the host service has already imported.

    Production uses Alembic migrations. Keeping model imports out of this
    platform helper lets `common/` stay domain-neutral when copied alone.
    """
    Base.metadata.create_all(_engine)

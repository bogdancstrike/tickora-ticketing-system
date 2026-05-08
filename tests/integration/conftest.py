from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from testcontainers.postgres import PostgresContainer

from src.core.db import Base
from src.iam.models import User
from src.iam.principal import Principal, ROLE_DISTRIBUTOR, SectorMembership
from src.ticketing.models import Beneficiary, Sector, Ticket


@pytest.fixture(scope="session")
def pg_engine() -> Iterator[Engine]:
    try:
        container = PostgresContainer("postgres:15-alpine")
        container.start()
    except Exception as exc:
        pytest.skip(f"Postgres testcontainer unavailable: {exc}")

    engine = create_engine(
        container.get_connection_url(),
        pool_size=60,
        max_overflow=20,
        pool_pre_ping=True,
        future=True,
    )
    try:
        yield engine
    finally:
        engine.dispose()
        container.stop()


@pytest.fixture
def db_session_factory(pg_engine: Engine) -> Iterator[sessionmaker[Session]]:
    Base.metadata.drop_all(pg_engine)
    Base.metadata.create_all(pg_engine)
    yield sessionmaker(bind=pg_engine, autoflush=False, autocommit=False, future=True)


@pytest.fixture
def db_session(db_session_factory: sessionmaker[Session]) -> Iterator[Session]:
    session = db_session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_user(db: Session, username: str, *, user_type: str = "internal") -> User:
    user = User(
        keycloak_subject=f"kc-{username}-{uuid.uuid4()}",
        username=username,
        email=f"{username}@example.test",
        first_name=username.title(),
        last_name="User",
        user_type=user_type,
    )
    db.add(user)
    db.flush()
    return user


def create_sector(db: Session, code: str = "s10") -> Sector:
    sector = Sector(code=code, name=f"Sector {code.upper()}", is_active=True)
    db.add(sector)
    db.flush()
    return sector


def create_beneficiary(db: Session, user: User) -> Beneficiary:
    beneficiary = Beneficiary(
        beneficiary_type=user.user_type,
        user_id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email,
    )
    db.add(beneficiary)
    db.flush()
    return beneficiary


def create_ticket(
    db: Session,
    beneficiary: Beneficiary,
    *,
    created_by: User,
    current_sector: Sector | None = None,
    status: str = "pending",
    assignee: User | None = None,
    last_active_assignee: User | None = None,
) -> Ticket:
    ticket = Ticket(
        ticket_code=f"TK-2026-{uuid.uuid4().int % 1_000_000:06d}",
        beneficiary_id=beneficiary.id,
        beneficiary_type=beneficiary.beneficiary_type,
        created_by_user_id=created_by.id,
        requester_first_name=beneficiary.first_name,
        requester_last_name=beneficiary.last_name,
        requester_email=beneficiary.email,
        current_sector_id=current_sector.id if current_sector else None,
        title="Connectivity outage",
        txt="The beneficiary reports a connectivity outage.",
        priority="high",
        status=status,
        assignee_user_id=assignee.id if assignee else None,
        last_active_assignee_user_id=last_active_assignee.id if last_active_assignee else None,
    )
    db.add(ticket)
    db.flush()
    return ticket


def principal_for(
    user: User,
    *,
    roles: set[str] | None = None,
    sectors: tuple[SectorMembership, ...] = (),
) -> Principal:
    return Principal(
        user_id=user.id,
        keycloak_subject=user.keycloak_subject,
        username=user.username,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        user_type=user.user_type,
        global_roles=frozenset(roles or set()),
        sector_memberships=sectors,
    )


def distributor_principal(user: User) -> Principal:
    return principal_for(user, roles={ROLE_DISTRIBUTOR})


def hydrate_ticket_for_assertion(db: Session, ticket_id: str) -> Ticket:
    db.execute(text("SELECT 1"))
    return db.get(Ticket, ticket_id)

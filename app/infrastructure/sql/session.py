from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


SqlSessionFactory = sessionmaker[Session]


def create_sql_engine(database_url: str, *, echo: bool = False) -> Engine:
    """Create the SQLAlchemy engine used by server/import tooling.

    No application/domain code should depend on the concrete engine. Production
    connection-pool settings can be supplied later by the server composition root.
    """

    return create_engine(database_url, echo=echo, future=True)


def create_session_factory(engine: Engine) -> SqlSessionFactory:
    """Return a factory with explicit transaction/commit semantics."""

    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


@contextmanager
def transactional_session(factory: SqlSessionFactory) -> Iterator[Session]:
    """Open one transaction and roll it back automatically on failure."""

    session = factory()
    try:
        with session.begin():
            yield session
    finally:
        session.close()

from celery import Task
from sqlalchemy import Engine
from sqlmodel import Session, create_engine

from backend.core.config import get_settings


class DatabaseTask(Task):
    """Base task giving access to a sync Session.

    The engine is created lazily on first use, i.e. inside the forked worker
    process, so each child process owns exactly one connection.
    """

    _engine: Engine | None = None

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            self._engine = create_engine(
                get_settings().database_url,
                pool_size=1,
                max_overflow=0,
                pool_pre_ping=True,
            )
        return self._engine

    def session(self) -> Session:
        return Session(self.engine)

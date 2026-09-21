from __future__ import annotations

from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory
from typing import Callable

from sqlalchemy.orm import Session

from app.infrastructure.sql import (
    Base,
    create_session_factory,
    create_sql_engine,
)


class SqliteDatabaseTemplate:
    """Build a seeded SQLite database once, then copy it for isolated tests."""

    def __init__(
        self,
        *,
        filename: str,
        seed: Callable[[Session], None],
    ) -> None:
        self._directory = TemporaryDirectory()
        self._filename = filename
        self._path = Path(self._directory.name) / filename
        url = f"sqlite:///{self._path.as_posix()}"
        engine = create_sql_engine(url)
        try:
            Base.metadata.create_all(engine)
            factory = create_session_factory(engine)
            with factory.begin() as session:
                seed(session)
        finally:
            engine.dispose()

    def copy_to(self, directory: str) -> str:
        path = Path(directory) / self._filename
        copyfile(self._path, path)
        return f"sqlite:///{path.as_posix()}"

    def cleanup(self) -> None:
        self._directory.cleanup()

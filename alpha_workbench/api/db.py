"""Database setup for the FastAPI product API."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

from alpha_workbench.api.config import settings


def _ensure_sqlite_parent(database_url: str) -> None:
    if not database_url.startswith("sqlite:///"):
        return
    db_path = Path(database_url.removeprefix("sqlite:///"))
    db_path.parent.mkdir(parents=True, exist_ok=True)


_ensure_sqlite_parent(settings.database_url)
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)


def init_db() -> None:
    # Import models before create_all so SQLModel metadata is populated.
    import alpha_workbench.api.models  # noqa: F401

    SQLModel.metadata.create_all(engine)
    _ensure_sqlite_schema_updates()


def _ensure_sqlite_schema_updates() -> None:
    if not settings.database_url.startswith("sqlite"):
        return
    with engine.begin() as connection:
        columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(research_runs)")).fetchall()
        }
        if "current_step" not in columns:
            connection.execute(
                text("ALTER TABLE research_runs ADD COLUMN current_step VARCHAR DEFAULT ''")
            )
        if "progress_events" not in columns:
            connection.execute(
                text("ALTER TABLE research_runs ADD COLUMN progress_events JSON DEFAULT '[]'")
            )


def get_db() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session

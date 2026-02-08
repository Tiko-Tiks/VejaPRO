from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

engine = None
if settings.database_url:
    connect_args: dict[str, object] = {}

    if settings.database_url.startswith("sqlite"):
        # Tests use SQLite and in-process ASGITransport. Starlette may run sync DB work in a
        # threadpool, so SQLite connections must be thread-safe. Timeout/busy_timeout reduce
        # flakes in concurrency/race tests.
        connect_args = {"check_same_thread": False, "timeout": 30}

    engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=connect_args)

    if settings.database_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection: Any, _connection_record: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine) if engine else None


def get_db() -> Generator[Session, None, None]:
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

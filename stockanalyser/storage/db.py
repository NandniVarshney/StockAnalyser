"""SQLAlchemy engine + session helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from stockanalyser.config import get_settings

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _ensure_engine() -> Engine:
    global _engine, _SessionLocal
    if _engine is None:
        settings = get_settings()
        sqlite_path = Path(settings.sqlite_path)
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(
            f"sqlite:///{sqlite_path}",
            connect_args={"check_same_thread": False},
            future=True,
        )
        _SessionLocal = sessionmaker(
            bind=_engine, autoflush=False, autocommit=False, expire_on_commit=False
        )
    return _engine


def init_db() -> None:
    """Create all tables. Idempotent."""
    from stockanalyser.storage.models import Base  # local import to avoid cycles

    engine = _ensure_engine()
    Base.metadata.create_all(engine)


@contextmanager
def get_session() -> Iterator[Session]:
    """Yield a session that auto-commits on success, rolls back on error."""
    _ensure_engine()
    assert _SessionLocal is not None
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

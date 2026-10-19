from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from doppelkopf_app.application.services import (
    GameSessionConfigurationError,
    SaveOutcomeUnknownError,
)


class Base(DeclarativeBase):
    pass


def _ensure_sqlite_parent(database_url: str) -> None:
    prefix = "sqlite:///"
    if database_url.startswith(prefix):
        Path(database_url.removeprefix(prefix)).parent.mkdir(parents=True, exist_ok=True)


def build_engine(database_url: str) -> Engine:
    _ensure_sqlite_parent(database_url)
    if database_url.startswith("sqlite"):
        return create_engine(database_url, connect_args={"check_same_thread": False})
    return create_engine(
        database_url,
        connect_args={"connect_timeout": 10},
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=5,
        max_overflow=5,
        pool_timeout=30,
    )


def create_schema(engine: Engine) -> None:
    from doppelkopf_app.infrastructure import models  # noqa: F401

    Base.metadata.create_all(engine)
    from doppelkopf_app.infrastructure.state_views import ROUND_VIEW_SQL, SESSION_VIEW_SQL

    with engine.begin() as connection:
        connection.exec_driver_sql(SESSION_VIEW_SQL)
        connection.exec_driver_sql(ROUND_VIEW_SQL)


def upgrade_schema(database_url: str) -> None:
    root = Path(__file__).resolve().parents[3]
    config = Config(root / "alembic.ini")
    config.attributes["database_url"] = database_url
    engine = build_engine(database_url)
    try:
        with engine.begin() as connection:
            _upgrade_with_lock(config, connection)
    finally:
        engine.dispose()


def migration_heads() -> tuple[str, ...]:
    """Return the migration heads used to invalidate cached runtime resources."""
    root = Path(__file__).resolve().parents[3]
    config = Config(root / "alembic.ini")
    return tuple(sorted(ScriptDirectory.from_config(config).get_heads()))


def _upgrade_with_lock(config: Config, connection: Connection) -> None:
    is_postgresql = connection.dialect.name == "postgresql"
    if is_postgresql:
        connection.exec_driver_sql("SET LOCAL lock_timeout = '15s'")
        connection.exec_driver_sql("SELECT pg_advisory_xact_lock(2026100201)")
    config.attributes["connection"] = connection
    command.upgrade(config, "head")


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def transaction(factory: sessionmaker[Session], *, snapshot: bool = False) -> Iterator[Session]:
    session = factory()
    try:
        if snapshot:
            if session.get_bind().dialect.name == "postgresql":
                session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
            else:
                session.connection().exec_driver_sql("BEGIN")
        yield session
        try:
            session.commit()
        except DBAPIError as error:
            if error.connection_invalidated:
                raise SaveOutcomeUnknownError(
                    "Die Speicherbestätigung fehlt. Bitte prüfe die aktualisierte "
                    "Spielliste, bevor du erneut speicherst."
                ) from error
            raise
    except DBAPIError as error:
        session.rollback()
        if getattr(error.orig, "sqlstate", None) in {"40001", "40P01"} or (
            getattr(error.orig, "sqlite_errorcode", None) in {5, 517}
        ):
            raise GameSessionConfigurationError(
                "Der Spielstand wurde gleichzeitig geändert. "
                "Bitte prüfe die aktuelle Anzeige und speichere erneut."
            ) from error
        raise
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

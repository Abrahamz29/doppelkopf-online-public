from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import Connection, Engine, select
from sqlalchemy.engine import make_url

from doppelkopf_app.config import normalize_database_url
from doppelkopf_app.infrastructure import models  # noqa: F401
from doppelkopf_app.infrastructure.database import Base, build_engine, upgrade_schema


@dataclass(frozen=True)
class SnapshotReport:
    """Verified result of copying the cloud database into an offline SQLite file."""

    destination_path: Path
    backup_path: Path | None
    table_counts: dict[str, int]
    digest: str


def load_neon_database_urls(env_file: Path) -> tuple[str, str]:
    """Load pooled and direct Neon URLs without exposing their values."""
    if not env_file.is_file():
        raise FileNotFoundError(f"Neon-Konfiguration fehlt: {env_file}")

    values: dict[str, str] = {}
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", maxsplit=1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key.strip()] = value

    application_url = values.get("DOKO_DATABASE_URL") or values.get("DATABASE_URL")
    migration_url = (
        values.get("DOKO_MIGRATION_DATABASE_URL")
        or values.get("DATABASE_URL_UNPOOLED")
        or application_url
    )
    if not application_url or not migration_url:
        raise ValueError(
            "Die Neon-Konfiguration benötigt DATABASE_URL und DATABASE_URL_UNPOOLED "
            "oder die entsprechenden DOKO_-Variablen."
        )

    normalized_application_url = normalize_database_url(application_url)
    normalized_migration_url = normalize_database_url(migration_url)
    if (
        make_url(normalized_application_url).get_backend_name() != "postgresql"
        or make_url(normalized_migration_url).get_backend_name() != "postgresql"
    ):
        raise ValueError("Die Snapshot-Quelle muss eine PostgreSQL-Datenbank sein.")
    return normalized_application_url, normalized_migration_url


def prepare_offline_snapshot(
    source_database_url: str,
    source_migration_database_url: str,
    destination_database_url: str,
    backup_directory: Path,
    *,
    root: Path,
) -> SnapshotReport:
    """Replace an offline SQLite database with a verified cloud snapshot."""
    destination_path = _sqlite_path(destination_database_url, root)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    backup_directory.mkdir(parents=True, exist_ok=True)
    temporary_path = destination_path.with_name(
        f".offline-snapshot-{uuid4().hex}{destination_path.suffix or '.db'}"
    )
    temporary_url = f"sqlite:///{temporary_path.as_posix()}"

    source_engine: Engine | None = None
    destination_engine: Engine | None = None
    try:
        try:
            upgrade_schema(source_migration_database_url)
            upgrade_schema(temporary_url)
            source_engine = build_engine(source_database_url)
            destination_engine = build_engine(temporary_url)
            table_counts, source_digest = _copy_tables(source_engine, destination_engine)
            copied_counts, copied_digest = _snapshot_signature(destination_engine)
            if copied_counts != table_counts or copied_digest != source_digest:
                raise RuntimeError(
                    "Die lokale Kopie stimmt nicht vollständig mit der Quelle überein."
                )
            _verify_sqlite_foreign_keys(destination_engine)
        finally:
            if destination_engine is not None:
                destination_engine.dispose()
            if source_engine is not None:
                source_engine.dispose()
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise

    backup_path = _backup_existing_database(destination_path, backup_directory)
    try:
        os.replace(temporary_path, destination_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise

    return SnapshotReport(
        destination_path=destination_path,
        backup_path=backup_path,
        table_counts=table_counts,
        digest=source_digest,
    )


def _sqlite_path(database_url: str, root: Path) -> Path:
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        raise ValueError("Das Offline-Ziel muss eine dateibasierte SQLite-Datenbank sein.")
    path = Path(url.database)
    return path if path.is_absolute() else (root / path).resolve()


def _copy_tables(source_engine: Engine, destination_engine: Engine) -> tuple[dict[str, int], str]:
    source_connection = source_engine.connect()
    try:
        if source_connection.dialect.name == "postgresql":
            source_connection = source_connection.execution_options(
                isolation_level="REPEATABLE READ"
            )
        with source_connection.begin(), destination_engine.begin() as destination:
            counts: dict[str, int] = {}
            digest = sha256()
            for table in Base.metadata.sorted_tables:
                rows = _ordered_rows(source_connection, table)
                if rows:
                    destination.execute(table.insert(), rows)
                counts[table.name] = len(rows)
                _update_digest(digest, table.name, rows)
        return counts, digest.hexdigest()
    finally:
        source_connection.close()


def _snapshot_signature(engine: Engine) -> tuple[dict[str, int], str]:
    counts: dict[str, int] = {}
    digest = sha256()
    with engine.connect() as connection:
        for table in Base.metadata.sorted_tables:
            rows = _ordered_rows(connection, table)
            counts[table.name] = len(rows)
            _update_digest(digest, table.name, rows)
    return counts, digest.hexdigest()


def _ordered_rows(connection: Connection, table: Any) -> list[dict[str, Any]]:
    primary_key = tuple(table.primary_key.columns)
    statement = select(table)
    if primary_key:
        statement = statement.order_by(*primary_key)
    return [dict(row) for row in connection.execute(statement).mappings()]


def _update_digest(digest: Any, table_name: str, rows: list[dict[str, Any]]) -> None:
    digest.update(table_name.encode("utf-8"))
    digest.update(b"\n")
    for row in rows:
        payload = {key: _json_value(value) for key, value in row.items()}
        digest.update(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        digest.update(b"\n")


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat(timespec="microseconds")
    if isinstance(value, date):
        return value.isoformat()
    return value


def _verify_sqlite_foreign_keys(engine: Engine) -> None:
    with engine.connect() as connection:
        violations = connection.exec_driver_sql("PRAGMA foreign_key_check").all()
    if violations:
        raise RuntimeError("Die lokale Kopie enthält ungültige Fremdschlüsselbeziehungen.")


def _backup_existing_database(destination_path: Path, backup_directory: Path) -> Path | None:
    if not destination_path.exists():
        return None
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")
    backup_path = backup_directory / f"doppelkopf-offline_{timestamp}.db"
    shutil.copy2(destination_path, backup_path)
    return backup_path

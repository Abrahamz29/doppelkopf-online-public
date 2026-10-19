"""A confirmed, explicit transaction over one psycopg pipeline exchange."""
from typing import Any, cast

import psycopg
from psycopg.pq import TransactionStatus
from psycopg.types.json import Jsonb
from sqlalchemy import Engine
from sqlalchemy.exc import DBAPIError

from doppelkopf_app.application.services import SaveOutcomeUnknownError

_UNKNOWN = (
    "Die Speicherbestätigung fehlt. Bitte prüfe die aktualisierte "
    "Spielliste, bevor du erneut speicherst."
)


def _exchange(connection: psycopg.Connection[Any], payload: dict[str, Any]) -> Any:
    """Queue all commands before fetching; leaving the pipeline waits for replies."""
    with connection.pipeline():
        connection.execute("BEGIN ISOLATION LEVEL REPEATABLE READ")
        result = connection.execute("SELECT save_round_v1(%s)", (Jsonb(payload),))
        confirmation = connection.execute("COMMIT")
    if (confirmation.statusmessage != "COMMIT"
            or connection.info.transaction_status != TransactionStatus.IDLE):
        raise SaveOutcomeUnknownError(_UNKNOWN)
    row = result.fetchone()
    if row is None:
        raise SaveOutcomeUnknownError(_UNKNOWN)
    return row[0]


def save_round_pipeline(engine: Engine, payload: dict[str, Any]) -> Any:
    """Retain pool health checks and return only after a confirmed atomic commit."""
    pooled = engine.raw_connection()
    connection = cast(psycopg.Connection[Any], pooled.driver_connection)
    previous_autocommit = connection.autocommit
    try:
        # Disable implicit driver BEGIN only. The explicit BEGIN above retains
        # REPEATABLE READ, parent locks and rollback of every write on SQL errors.
        connection.autocommit = True
        return _exchange(connection, payload)
    except psycopg.Error as error:
        if connection.closed or error.sqlstate is None:
            pooled.invalidate(error)
            raise SaveOutcomeUnknownError(_UNKNOWN) from error
        raise DBAPIError("save_round_v1", None, error) from error
    finally:
        if not connection.closed:
            try:
                if connection.info.transaction_status != TransactionStatus.IDLE:
                    connection.rollback()
                connection.autocommit = previous_autocommit
            except psycopg.Error as cleanup_error:
                # Never put a broken/aborted connection back into the shared pool.
                pooled.invalidate(cleanup_error)
        pooled.close()

import streamlit as st
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from doppelkopf_app.application.services import DoppelkopfService
from doppelkopf_app.config import get_settings
from doppelkopf_app.infrastructure.database import (
    build_engine,
    migration_heads,
    session_factory,
    upgrade_schema,
)
from doppelkopf_app.infrastructure.repositories import SqlAlchemyDoppelkopfRepository


@st.cache_resource
def database_resources(schema_heads: tuple[str, ...]) -> tuple[Engine, sessionmaker[Session]]:
    if not schema_heads:
        raise RuntimeError("Keine Alembic-Migration gefunden.")
    settings = get_settings()
    database_url = settings.normalized_database_url
    upgrade_schema(settings.normalized_migration_database_url)
    engine = build_engine(database_url)
    return engine, session_factory(engine)


def get_session_factory() -> sessionmaker[Session]:
    return database_resources(migration_heads())[1]


def get_service() -> DoppelkopfService:
    return DoppelkopfService(SqlAlchemyDoppelkopfRepository(get_session_factory()))

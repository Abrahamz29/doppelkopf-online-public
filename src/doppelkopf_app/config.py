from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_database_url(database_url: str) -> str:
    """Select psycopg 3 explicitly for PostgreSQL URLs supplied by hosting providers."""
    normalized = database_url.strip()
    if normalized.startswith("postgres://"):
        return "postgresql+psycopg://" + normalized.removeprefix("postgres://")
    if normalized.startswith("postgresql://"):
        return "postgresql+psycopg://" + normalized.removeprefix("postgresql://")
    return normalized


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or a local .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="DOKO_", extra="ignore")

    database_url: str = "sqlite:///data/doppelkopf.db"
    migration_database_url: str | None = None
    offline_mode: bool = False
    offline_database_url: str = "sqlite:///data/doppelkopf-offline.db"
    app_password: str | None = None
    app_password_required: bool = False
    environment: str = "development"
    log_level: str = "INFO"
    tempo_window_minutes: int = 30
    public_base_url: str | None = None

    @property
    def normalized_database_url(self) -> str:
        database_url = self.offline_database_url if self.offline_mode else self.database_url
        return normalize_database_url(database_url)

    @property
    def normalized_migration_database_url(self) -> str:
        if self.offline_mode:
            return normalize_database_url(self.offline_database_url)
        return normalize_database_url(self.migration_database_url or self.database_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()

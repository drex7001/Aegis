"""Runtime settings, sourced from env vars, repo-root .env, and infra/.runtime.env
(the latter is written by `make bootstrap` with FGA store/model ids)."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "infra/.runtime.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(
        default="postgresql+psycopg://aegis:aegis-dev@localhost:5433/aegis",
        validation_alias="AEGIS_DATABASE_URL",
    )
    ontology_path: str = Field(default="ontology/aegis.yaml", validation_alias="AEGIS_ONTOLOGY_PATH")

    fga_api_url: str = Field(default="http://localhost:8082", validation_alias="FGA_API_URL")
    fga_store_id: str | None = Field(default=None, validation_alias="FGA_STORE_ID")
    fga_model_id: str | None = Field(default=None, validation_alias="FGA_MODEL_ID")

    keycloak_url: str = Field(default="http://localhost:8180", validation_alias="KEYCLOAK_URL")
    keycloak_realm: str = Field(default="aegis", validation_alias="KEYCLOAK_REALM")

    minio_endpoint: str = Field(default="localhost:9000", validation_alias="MINIO_ENDPOINT")
    minio_access_key: str = Field(default="aegis", validation_alias="MINIO_ROOT_USER")
    minio_secret_key: str = Field(default="aegis-minio-dev", validation_alias="MINIO_ROOT_PASSWORD")


@lru_cache
def get_settings() -> Settings:
    return Settings()

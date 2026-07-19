"""Runtime settings, sourced from env vars, repo-root .env, and infra/.runtime.env
(the latter is written by `make bootstrap` with FGA store/model ids).

**Every local default is `127.0.0.1`, never `localhost`.**  On Windows
`localhost` resolves to `::1` first, and the compose port publishes on IPv4
only, so each connection stalls on a failed IPv6 attempt before falling back.
Measured on the dev stack: **2.05 s per connection via `localhost` vs 0.01 s
via `127.0.0.1`** — a 200x difference that is invisible per call and dominates
anything connection-heavy (the integration suite spent roughly 80 minutes of a
two-hour run inside it).  Keep the literal address; if a service ever needs to
be reachable over IPv6, set it explicitly through the env var.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "infra/.runtime.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(
        default="postgresql+psycopg://aegis:aegis-dev@127.0.0.1:5433/aegis",
        validation_alias="AEGIS_DATABASE_URL",
    )
    ontology_path: str = Field(default="ontology/aegis.yaml", validation_alias="AEGIS_ONTOLOGY_PATH")

    fga_api_url: str = Field(default="http://127.0.0.1:8082", validation_alias="FGA_API_URL")
    fga_store_id: str | None = Field(default=None, validation_alias="FGA_STORE_ID")
    fga_model_id: str | None = Field(default=None, validation_alias="FGA_MODEL_ID")
    authz_outbox_interval_seconds: float = Field(
        default=5.0,
        gt=0,
        validation_alias="AEGIS_AUTHZ_OUTBOX_INTERVAL_SECONDS",
    )
    authz_outbox_batch_size: int = Field(
        default=100,
        ge=1,
        validation_alias="AEGIS_AUTHZ_OUTBOX_BATCH_SIZE",
    )

    # Deliberately NOT 127.0.0.1, unlike every other local default above. This
    # URL is an *identity*, not just an address: it is the OIDC issuer, and it
    # must match the `iss` claim Keycloak mints (its configured hostname) byte
    # for byte or every token fails validation. Changing it to a literal IP
    # turns all authenticated requests into 401s.
    keycloak_url: str = Field(default="http://localhost:8180", validation_alias="KEYCLOAK_URL")
    keycloak_realm: str = Field(default="aegis", validation_alias="KEYCLOAK_REALM")
    api_audience: str = Field(default="aegis-api", validation_alias="AEGIS_API_AUDIENCE")
    # Tolerated clock difference between Keycloak and this process when checking
    # `exp`, `nbf` and `iat`. Zero looks stricter but is not safer: the identity
    # provider is a different host, so a second of NTP drift makes every freshly
    # minted token "not yet valid" and the platform simply stops working. RFC
    # 7519 §4.1.4 anticipates exactly this. Measured on the dev stack: the
    # Keycloak container ran ~2s ahead of the host.
    oidc_clock_skew_seconds: int = Field(
        default=60,
        ge=0,
        le=300,
        validation_alias="AEGIS_OIDC_CLOCK_SKEW_SECONDS",
    )

    # Per authenticated caller, applied to every route (specs/06 §1 default 6).
    # Replaces the per-IP cap T16a put on the anonymous /api/* routes, which
    # T22 deleted with the routes themselves.
    api_rate_limit_per_minute: int = Field(
        default=600,
        ge=1,
        validation_alias="AEGIS_API_RATE_LIMIT_PER_MINUTE",
    )

    minio_endpoint: str = Field(default="127.0.0.1:9000", validation_alias="MINIO_ENDPOINT")
    minio_access_key: str = Field(default="aegis", validation_alias="MINIO_ROOT_USER")
    minio_secret_key: str = Field(default="aegis-minio-dev", validation_alias="MINIO_ROOT_PASSWORD")
    minio_bucket: str = Field(default="evidence", validation_alias="MINIO_EVIDENCE_BUCKET")
    minio_secure: bool = Field(default=False, validation_alias="MINIO_SECURE")

    vault_backend: Literal["minio", "filesystem"] = Field(
        default="minio", validation_alias="AEGIS_VAULT_BACKEND"
    )
    vault_local_path: str = Field(default=".aegis/vault", validation_alias="AEGIS_VAULT_PATH")


@lru_cache
def get_settings() -> Settings:
    return Settings()

"""Environment-based configuration. Every secret comes from the environment; nothing is hard-coded."""

from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-only-change-me-please-32-bytes-min"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Netra CCTV Intelligence Platform"
    environment: str = "development"
    log_level: str = "INFO"
    api_docs_enabled: bool = True  # set false on internet-facing deployments

    # Database / cache
    database_url: str = "sqlite+aiosqlite:///./netra.db"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    redis_url: str = ""  # empty -> in-process fallbacks (tests / single-node dev)

    # Security
    jwt_secret: str = Field(default=DEV_JWT_SECRET, min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 480
    stream_token_seconds: int = 300
    # Fernet key (urlsafe base64, 32 bytes) used to encrypt camera stream credentials at rest
    credentials_key: str = ""
    cors_origins: str = "http://localhost:5173,https://localhost"
    rate_limit_login_per_min: int = 10
    rate_limit_ingest_per_min: int = 6000
    rate_limit_api_per_min: int = 600

    # Bootstrap accounts (only used by the seed script, never logged)
    admin_username: str = "admin"
    admin_password: str = ""
    operator_password: str = ""
    viewer_password: str = ""
    seed_api_key: str = ""  # API key for analytics/edge simulators

    # Video gateway (MediaMTX)
    gateway_api_url: str = "http://gateway:9997"
    gateway_public_hls_base: str = "/media"
    gateway_playback_url: str = "http://gateway:9996"
    gateway_public_playback_base: str = "/playback"
    gateway_enabled: bool = True
    gateway_api_user: str = "netra-backend"
    gateway_api_secret: str = ""  # authenticates the backend to the gateway control API
    stream_on_demand: bool = False

    # Health monitor
    health_interval_seconds: int = 10
    heartbeat_degraded_after_s: int = 30
    heartbeat_offline_after_s: int = 90
    probe_timeout_s: float = 3.0
    probe_slow_threshold_s: float = 1.5
    position_retention_hours: int = 48  # dashcam GPS track history
    event_retention_days: int = 30  # detection history (events behind alerts are always kept)

    # Ingestion / correlation
    dedup_window_seconds: int = 60
    alert_cooldown_seconds: int = 300
    min_match_confidence: float = 0.60
    fuzzy_match_enabled: bool = True
    max_event_age_hours: int = 72
    max_future_skew_seconds: int = 300
    stream_ingest_enabled: bool = True
    stream_ingest_key: str = "netra:ingest:detections"

    # SSRF guard: platform services that must never be used as camera endpoints
    blocked_endpoint_hosts: str = "localhost,backend,mysql,redis,gateway,web,prometheus,metadata.google.internal"

    # ONVIF discovery targets (WS-Discovery multicast does not cross Docker bridges)
    onvif_discovery_hosts: str = ""

    @model_validator(mode="after")
    def no_dev_secrets_in_production(self):
        if self.environment == "production" and self.jwt_secret == DEV_JWT_SECRET:
            raise ValueError("JWT_SECRET must be set in production")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def onvif_host_list(self) -> list[str]:
        return [h.strip() for h in self.onvif_discovery_hosts.split(",") if h.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

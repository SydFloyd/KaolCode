from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


RunMode = Literal["fast", "release"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_env: str = Field(default="dev", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    database_url: str = Field(
        default="postgresql+psycopg://codex:codex@localhost:5432/codex",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    queue_name: str = Field(default="jobs", alias="QUEUE_NAME")

    webhook_secret: str = Field(default="", alias="WEBHOOK_SECRET")
    operator_token: str = Field(default="replace_me", alias="OPERATOR_TOKEN")

    policy_path: str = Field(default="config/policy.yaml", alias="POLICY_PATH")
    repos_path: str = Field(default="config/repos.yaml", alias="REPOS_PATH")
    artifact_root: str = Field(default="data/artifacts", alias="ARTIFACT_ROOT")

    auto_migrate: bool = Field(default=True, alias="AUTO_MIGRATE")
    disable_queue: bool = Field(default=False, alias="DISABLE_QUEUE")
    run_mode: RunMode = Field(default="fast", alias="RUN_MODE")
    queue_retry_max: int = Field(default=2, alias="QUEUE_RETRY_MAX", ge=0, le=10)
    queue_retry_intervals: list[int] = Field(default_factory=lambda: [30, 120], alias="QUEUE_RETRY_INTERVALS")
    queue_job_timeout_seconds: int = Field(default=3600, alias="QUEUE_JOB_TIMEOUT_SECONDS", ge=60, le=7200)
    queue_result_ttl_seconds: int = Field(default=86400, alias="QUEUE_RESULT_TTL_SECONDS", ge=0)
    queue_failure_ttl_seconds: int = Field(default=1209600, alias="QUEUE_FAILURE_TTL_SECONDS", ge=0)

    max_usd_per_day: float = Field(default=40.0, alias="MAX_USD_PER_DAY")
    max_usd_per_month: float = Field(default=900.0, alias="MAX_USD_PER_MONTH")

    model_triage: str = Field(default="gpt-4o-mini", alias="MODEL_TRIAGE")
    model_build: str = Field(default="gpt-4.1", alias="MODEL_BUILD")
    model_review: str = Field(default="gpt-4.1-mini", alias="MODEL_REVIEW")

    litellm_base_url: str = Field(default="http://localhost:4000", alias="LITELLM_BASE_URL")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    litellm_api_key: str = Field(default="", alias="LITELLM_API_KEY")

    github_app_id: str = Field(default="", alias="GITHUB_APP_ID")
    github_app_installation_id: str = Field(default="", alias="GITHUB_APP_INSTALLATION_ID")
    github_app_private_key_pem: str = Field(default="", alias="GITHUB_APP_PRIVATE_KEY_PEM")

    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8080, alias="API_PORT")
    worker_metrics_host: str = Field(default="0.0.0.0", alias="WORKER_METRICS_HOST")
    worker_metrics_port: int = Field(default=9108, alias="WORKER_METRICS_PORT", ge=1, le=65535)
    worker_metrics_enabled: bool = Field(default=True, alias="WORKER_METRICS_ENABLED")

    @field_validator("run_mode", mode="before")
    @classmethod
    def normalize_run_mode(cls, value):
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("queue_retry_intervals", mode="before")
    @classmethod
    def normalize_retry_intervals(cls, value):
        if value is None:
            return [30, 120]
        if isinstance(value, str):
            parts = [entry.strip() for entry in value.split(",") if entry.strip()]
            if not parts:
                return [30, 120]
            return [max(1, int(part)) for part in parts]
        if isinstance(value, list):
            if not value:
                return [30, 120]
            return [max(1, int(part)) for part in value]
        return value

    def is_fast_mode(self) -> bool:
        return self.run_mode == "fast"

    def is_release_mode(self) -> bool:
        return self.run_mode == "release"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

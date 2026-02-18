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

    @field_validator("run_mode", mode="before")
    @classmethod
    def normalize_run_mode(cls, value):
        if isinstance(value, str):
            return value.strip().lower()
        return value

    def is_fast_mode(self) -> bool:
        return self.run_mode == "fast"

    def is_release_mode(self) -> bool:
        return self.run_mode == "release"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

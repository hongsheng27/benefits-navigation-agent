"""Application configuration loaded from environment variables.

Values come from the process environment or a `.env` file. Never commit real
credentials; see `.env.example` at the repository root for the expected
variable names.

Both the repository-root `.env` and a `backend/.env` are read, in that order,
so a single root file works while still allowing a backend-only override.

Unknown variables are ignored rather than rejected, because the root `.env` is
shared with the Vite frontend and contains `VITE_`-prefixed names.
"""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven settings for the FastAPI application."""

    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        extra="ignore",
    )

    environment: str = "local"

    # The calendar that same-day refresh dedup is measured against. Refresh
    # jobs are deduplicated per source per event per *local* calendar date, so
    # this value decides where the day boundary falls. Using UTC would move the
    # boundary to 08:00 local time in Taiwan and silently allow a second crawl
    # of the same source on the same working day.
    application_timezone: str = "Asia/Taipei"

    # --- Data store backend selector ---
    # "sqlite" (default, local development) or "postgresql" (RDS deployment).
    data_store_backend: str = "sqlite"

    # --- RDS PostgreSQL settings (only used when data_store_backend=postgresql) ---
    rds_host: str = ""
    rds_port: int = 5432
    rds_database: str = "benefits_navigation"
    rds_username: str = "benefits_admin"
    rds_password: str = ""
    rds_sslmode: str = "require"

    # --- AWS region ---
    aws_region: str = "us-west-2"

    # Vite's development server. Deployment origins are added once the
    # deployment platform is decided.
    cors_allow_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # --- AWS / Bedrock -----------------------------------------------------
    #
    # Competition primary regions are us-east-1 and us-west-2. Workshop
    # accounts often hand out temporary keys as PowerShell `$Env:...` lines;
    # the same names can be pasted into `.env` instead. `get_settings()` then
    # copies them into `os.environ` so boto3 can see them.

    aws_region: str = "us-west-2"
    """AWS region for Bedrock and other AWS clients.

    us-west-2 is the team default: it is the region the Bedrock path was first
    verified in and the one `.env.example` and the migration guide name. us-east-1
    is also verified and works, but keep one answer in one place — a region that
    differs between the code default, `.env.example`, and a teammate's shell is a
    slow bug to find.
    """

    aws_default_region: str = ""
    """Optional alias for workshop snippets that set AWS_DEFAULT_REGION."""

    aws_access_key_id: str = ""
    """Temporary or long-lived access key. Never commit a real value."""

    aws_secret_access_key: str = ""
    """Secret key paired with aws_access_key_id. Never commit a real value."""

    aws_session_token: str = ""
    """Session token for workshop / STS temporary credentials."""

    bedrock_model_id: str = ""
    """Bedrock model or inference profile ID. Empty means Bedrock is not selected.

    Request access only for the model you actually use (competition rule).
    Verified example: us.anthropic.claude-haiku-4-5-20251001-v1:0
    """

    def has_bedrock_language_model(self) -> bool:
        """Whether a Bedrock model ID is configured."""
        return bool(self.bedrock_model_id.strip())

    def has_live_language_model(self) -> bool:
        """Whether the Bedrock live model is configured.

        `strip()` because an accidental `BEDROCK_MODEL_ID=" "` in `.env` should
        count as absent rather than produce a failed call on every request.
        """
        return self.has_bedrock_language_model()


def apply_aws_credentials_to_environ(settings: Settings) -> None:
    """Copy AWS fields from Settings into `os.environ` for boto3.

    boto3 only reads the process environment and shared config files — it does
    not know about pydantic-settings. Workshop credentials pasted into `.env`
    therefore have to be published here once per process.
    """
    region = settings.aws_default_region.strip() or settings.aws_region.strip()
    if region:
        os.environ["AWS_REGION"] = region
        os.environ["AWS_DEFAULT_REGION"] = region

    if settings.aws_access_key_id.strip():
        os.environ["AWS_ACCESS_KEY_ID"] = settings.aws_access_key_id.strip()
    if settings.aws_secret_access_key.strip():
        os.environ["AWS_SECRET_ACCESS_KEY"] = settings.aws_secret_access_key.strip()
    if settings.aws_session_token.strip():
        os.environ["AWS_SESSION_TOKEN"] = settings.aws_session_token.strip()


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    settings = Settings()
    apply_aws_credentials_to_environ(settings)
    return settings

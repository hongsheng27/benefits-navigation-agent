"""Application configuration loaded from environment variables.

Values come from the process environment or a `.env` file. Never commit real
credentials; see `.env.example` at the repository root for the expected
variable names.

Both the repository-root `.env` and a `backend/.env` are read, in that order,
so a single root file works while still allowing a backend-only override.

Unknown variables are ignored rather than rejected, because the root `.env` is
shared with the Vite frontend and contains `VITE_`-prefixed names.
"""

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

    # Vite's development server. Deployment origins are added once the
    # deployment platform is decided.
    cors_allow_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()

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

    # Vite's development server. Deployment origins are added once the
    # deployment platform is decided.
    cors_allow_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # --- Language model ----------------------------------------------------
    #
    # Empty means no live model. The backend then falls back to an offline
    # implementation instead of failing to start, so a teammate without a key
    # can still run everything (ADR-0015).

    gemini_api_key: str = ""
    """Gemini API key. Never commit a real value; keep it in a local `.env`."""

    gemini_model_id: str = "gemma-4-31b-it"
    """Model identifier, configurable because models get retired.

    Hardcoding it means the backend breaks one day for a reason that is not
    visible in the error.

    Both `gemma-4-31b-it` and `gemini-3.6-flash` were verified against the live
    API on 2026-07-30: each returns schema-conforming JSON through the
    interactions endpoint, and each correctly answers `unrecognised` for a
    description that maps to no registered event.
    """

    def has_live_language_model(self) -> bool:
        """Whether a real model is configured.

        `strip()` because an accidental `GEMINI_API_KEY=" "` in `.env` should
        count as absent rather than produce a 401 on every request.
        """
        return bool(self.gemini_api_key.strip())


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()

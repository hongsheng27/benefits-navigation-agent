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

    # --- AWS / Bedrock -----------------------------------------------------
    #
    # Competition primary regions are us-east-1 and us-west-2. Default to
    # us-east-1. Credentials come from the normal AWS chain (env vars, shared
    # config, or instance role) — never commit keys.

    aws_region: str = "us-east-1"
    """AWS region for Bedrock and other AWS clients."""

    bedrock_model_id: str = ""
    """Bedrock foundation model ID. Empty means Bedrock is not selected.

    Request access only for the model you actually use (competition rule).
    Example on us-east-1: anthropic.claude-3-haiku-20240307-v1:0
    """

    # --- Gemini (fallback while Bedrock is unavailable) --------------------
    #
    # Empty means no Gemini key. Used only when Bedrock is not configured.

    gemini_api_key: str = ""
    """Gemini API key. Never commit a real value; keep it in a local `.env`."""

    gemini_model_id: str = "gemma-4-31b-it"
    """Model identifier, configurable because models get retired."""

    def has_bedrock_language_model(self) -> bool:
        """Whether a Bedrock model ID is configured."""
        return bool(self.bedrock_model_id.strip())

    def has_gemini_language_model(self) -> bool:
        """Whether a Gemini API key is configured."""
        return bool(self.gemini_api_key.strip())

    def has_live_language_model(self) -> bool:
        """Whether any real model is configured (Bedrock preferred, else Gemini).

        `strip()` because an accidental `BEDROCK_MODEL_ID=" "` in `.env` should
        count as absent rather than produce a failed call on every request.
        """
        return self.has_bedrock_language_model() or self.has_gemini_language_model()


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()

"""FastAPI application entry point.

Keep this module at the HTTP transport boundary. Application services,
workflow transitions, eligibility rules, retrieval, and Agent integration
belong in their dedicated modules rather than route handlers.

Routers live in `app.api`. This module only builds the application and wires
middleware, so that adding an endpoint never requires editing business logic.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import install_error_handlers
from app.api.health import router as health_router
from app.api.sessions import router as sessions_router
from app.application.composition import (
    ApplicationOverrides,
    build_dependencies,
)
from app.config import get_settings
from app.llm.factory import build_language_model
from app.observability.logging import configure_logging
from app.orchestration.session_store import InMemorySessionStore


def create_app(
    overrides: ApplicationOverrides | None = None,
    *,
    db_path: Path | None = None,
) -> FastAPI:
    """Build the FastAPI application.

    Exposed as a factory so tests and future deployment adapters can build an
    isolated instance instead of importing shared module state.

    Parameters
    ----------
    overrides:
        Optional fake implementations for testing. When all four ports are
        provided, ZERO SQLite connections are opened (Req 2.9).
    db_path:
        Override the default SQLite database path (useful for tests).
    """
    configure_logging()
    settings = get_settings()

    app = FastAPI(
        title="接住 Benefits Navigation API",
        version="0.1.0",
    )

    # Credentials stay off: the session identifier travels in the request body
    # or an explicit header, never in cookies. See ADR-0005.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Session state lives on the application instance rather than in module
    # state, so each create_app() call is isolated. It is in-memory only: a
    # restart discards every session, which ADR-0005 treats as acceptable
    # because persistence is still undecided.
    app.state.session_store = InMemorySessionStore()

    # --- Composition root: build all dependencies before accepting requests ---
    # DependencyConfigurationError propagates as a startup failure (Req 2.10).
    deps = build_dependencies(overrides, db_path=db_path)
    app.state.dependencies = deps

    # Chosen once at startup, not per request: whether a live model is
    # available does not change while the process runs, and re-deciding per
    # request would make it possible for one request to use the real model and
    # the next to silently use demo data. See ADR-0015.
    app.state.language_model = build_language_model(settings)

    install_error_handlers(app)

    app.include_router(health_router)
    app.include_router(sessions_router)

    return app


app = create_app()

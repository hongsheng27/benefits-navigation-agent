"""FastAPI application entry point.

Keep this module at the HTTP transport boundary. Application services,
workflow transitions, eligibility rules, retrieval, and Agent integration
belong in their dedicated modules rather than route handlers.

Routers live in `app.api`. This module only builds the application and wires
middleware, so that adding an endpoint never requires editing business logic.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import install_error_handlers
from app.api.health import router as health_router
from app.api.sessions import router as sessions_router
from app.config import get_settings
from app.observability.logging import configure_logging
from app.orchestration.session_store import InMemorySessionStore


def create_app() -> FastAPI:
    """Build the FastAPI application.

    Exposed as a factory so tests and future deployment adapters can build an
    isolated instance instead of importing shared module state.
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

    install_error_handlers(app)

    app.include_router(health_router)
    app.include_router(sessions_router)

    return app


app = create_app()

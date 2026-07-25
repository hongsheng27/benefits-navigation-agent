"""FastAPI application entry point.

Keep this module at the HTTP transport boundary. Application services,
workflow transitions, eligibility rules, retrieval, and Agent integration
belong in their dedicated modules rather than route handlers.

Routers live in `app.api`. This module only builds the application and wires
middleware, so that adding an endpoint never requires editing business logic.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.config import get_settings


def create_app() -> FastAPI:
    """Build the FastAPI application.

    Exposed as a factory so tests and future deployment adapters can build an
    isolated instance instead of importing shared module state.
    """
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

    app.include_router(health_router)

    return app


app = create_app()

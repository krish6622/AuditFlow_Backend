"""FastAPI application factory and entrypoint.

Run locally with:  uvicorn app.main:app --reload --port 8000
OpenAPI docs:       http://localhost:8000/docs
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version="1.0.0",
        description=(
            "Multi-tenant SaaS for field-service businesses: employees, "
            "work orders, and invoices."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    @app.get("/", tags=["Health"])
    def root() -> dict[str, str]:
        return {"service": settings.APP_NAME, "status": "ok"}

    @app.get("/health", tags=["Health"])
    def health() -> dict[str, str]:
        return {"status": "healthy", "environment": settings.ENVIRONMENT}

    logger.info("%s started (env=%s)", settings.APP_NAME, settings.ENVIRONMENT)
    return app


app = create_app()

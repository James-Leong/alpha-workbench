"""FastAPI entrypoint for the AlphaWorkbench product website."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from alpha_workbench.api.db import init_db
from alpha_workbench.api.routers import auth, research
from alpha_workbench.api.schemas import HealthResponse
from alpha_workbench.core.config import settings
from alpha_workbench.core.logging import configure_logging


configure_logging()


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db()
        yield

    app = FastAPI(title=f"{settings.app_name} API", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.app_secret_key,
        same_site="lax",
        https_only=settings.cookie_secure,
    )

    @app.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok", app=settings.app_name)

    app.include_router(auth.router)
    app.include_router(research.router)
    return app


app = create_app()

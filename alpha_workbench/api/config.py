"""Configuration for the AlphaWorkbench FastAPI product API."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[2]


def _getenv(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def _bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class ApiSettings:
    app_name: str
    app_secret_key: str
    environment: str
    database_url: str
    frontend_base_url: str
    backend_base_url: str
    allowed_origins: list[str]
    session_cookie_name: str
    session_ttl_hours: int
    cookie_secure: bool
    github_client_id: str
    github_client_secret: str

    @property
    def is_dev(self) -> bool:
        return self.environment in {"development", "dev", "local"}


def load_api_settings() -> ApiSettings:
    load_dotenv()
    data_dir = Path(_getenv("DATA_DIR", str(ROOT_DIR / "data")))
    default_db = f"sqlite:///{data_dir / 'alpha_workbench.sqlite3'}"
    frontend_base_url = _getenv("FRONTEND_BASE_URL", "http://localhost:5173")
    backend_base_url = _getenv("BACKEND_BASE_URL", "http://localhost:8000")
    allowed_origins = [
        origin.strip()
        for origin in _getenv(
            "CORS_ALLOWED_ORIGINS",
            f"{frontend_base_url},http://localhost:3000",
        ).split(",")
        if origin.strip()
    ]
    environment = _getenv("ENV", "development").lower()
    secret = _getenv("APP_SECRET_KEY", "dev-only-change-me")
    return ApiSettings(
        app_name=_getenv("APP_NAME", "AlphaWorkbench"),
        app_secret_key=secret,
        environment=environment,
        database_url=_getenv("DATABASE_URL", default_db),
        frontend_base_url=frontend_base_url.rstrip("/"),
        backend_base_url=backend_base_url.rstrip("/"),
        allowed_origins=allowed_origins,
        session_cookie_name=_getenv("SESSION_COOKIE_NAME", "aw_session"),
        session_ttl_hours=int(_getenv("SESSION_TTL_HOURS", "168")),
        cookie_secure=_bool(_getenv("COOKIE_SECURE", "false")),
        github_client_id=_getenv("GITHUB_CLIENT_ID", ""),
        github_client_secret=_getenv("GITHUB_CLIENT_SECRET", ""),
    )


settings = load_api_settings()

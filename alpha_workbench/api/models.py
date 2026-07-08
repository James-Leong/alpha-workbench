"""SQLite models for users, sessions, OAuth accounts, and research runs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Column, JSON, UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    username: str = Field(index=True, unique=True)
    password_hash: str | None = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class UserSession(SQLModel, table=True):
    __tablename__ = "user_sessions"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    token_hash: str = Field(index=True, unique=True)
    csrf_token: str = Field(index=True)
    expires_at: datetime = Field(index=True)
    created_at: datetime = Field(default_factory=utcnow)
    last_seen_at: datetime = Field(default_factory=utcnow)


class OAuthAccount(SQLModel, table=True):
    __tablename__ = "oauth_accounts"
    __table_args__ = (UniqueConstraint("provider", "provider_account_id"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    provider: str = Field(index=True)
    provider_account_id: str = Field(index=True)
    email: str | None = Field(default=None, index=True)
    username: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class ResearchProject(SQLModel, table=True):
    __tablename__ = "research_projects"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    title: str
    idea_text: str
    status: str = Field(default="completed", index=True)
    summary: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class ResearchRun(SQLModel, table=True):
    __tablename__ = "research_runs"

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="research_projects.id", index=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    input_text: str
    status: str = Field(default="completed", index=True)
    workflow_mode: str = "demo_workflow"
    is_mock: bool = True
    current_step: str = ""
    progress_events: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    duration_ms: int = 0
    error: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class ResearchTrace(SQLModel, table=True):
    __tablename__ = "research_traces"

    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="research_runs.id", index=True, unique=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    trace_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    report_markdown: str = ""
    metrics_summary: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utcnow)

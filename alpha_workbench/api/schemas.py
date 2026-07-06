"""API request and response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field


class UserRead(BaseModel):
    id: int
    email: str
    username: str
    csrf_token: str


class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=2, max_length=40)
    password: str = Field(min_length=8, max_length=256)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class ResearchProjectCreate(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    input_text: str = Field(min_length=4, max_length=8000)


class ResearchProjectSummary(BaseModel):
    id: int
    title: str
    idea_text: str
    status: str
    summary: str
    created_at: datetime
    updated_at: datetime
    latest_run_id: int | None = None
    current_step: str = ""
    progress_events: list[dict[str, Any]] = Field(default_factory=list)


class ResearchProjectDetail(ResearchProjectSummary):
    report_markdown: str = ""
    metrics_summary: dict[str, Any] = Field(default_factory=dict)
    trace: dict[str, Any] = Field(default_factory=dict)


class ResearchSpecUpdate(BaseModel):
    universe: str | None = None
    rebalance_frequency: str | None = None
    holding_period: str | None = None
    transaction_cost_bps: float | None = None
    benchmark: str | None = None
    initial_cash: float | None = None
    sample_window_start: str | None = None
    sample_window_end: str | None = None
    filters: list[str] | None = None


class ResearchRunProgress(BaseModel):
    project_id: int
    run_id: int | None = None
    status: str
    current_step: str = ""
    progress_events: list[dict[str, Any]] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    app: str

"""Pydantic contracts shared by factor plugin tooling and the runtime."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FactorCodingBrief(_ContractModel):
    """Structured implementation request passed to a factor coding agent."""

    factor_id: str = Field(min_length=1)
    idea_summary: str = Field(min_length=1)
    hypothesis: str = Field(min_length=1)
    required_fields: list[str] = Field(default_factory=list)
    data_policy: dict[str, Any] = Field(default_factory=dict)
    implementation_target: Literal["python_plugin"] = "python_plugin"
    plugin_contract: dict[str, Any] = Field(default_factory=dict)
    test_requirements: list[str] = Field(default_factory=list)

    @field_validator("required_fields")
    @classmethod
    def validate_required_fields(cls, fields: list[str]) -> list[str]:
        if any(not field.strip() for field in fields):
            raise ValueError("required_fields cannot contain blank names")
        if len(fields) != len(set(fields)):
            raise ValueError("required_fields must be unique")
        return fields


class FactorPluginManifest(_ContractModel):
    """Versioned metadata and data requirements for one factor plugin."""

    factor_id: str = Field(min_length=1)
    factor_name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    entrypoint: str = Field(min_length=1)
    required_fields: list[str] = Field(default_factory=list)
    lookback_days: int = Field(default=0, ge=0)
    frequency: str = Field(default="daily", min_length=1)
    point_in_time: bool = True
    parameters: dict[str, Any] = Field(default_factory=dict)
    data_policy: dict[str, Any] = Field(default_factory=dict)
    risk_notes: list[str] = Field(default_factory=list)
    status: str = Field(default="generated", min_length=1)

    @field_validator("required_fields")
    @classmethod
    def validate_required_fields(cls, fields: list[str]) -> list[str]:
        if any(not field.strip() for field in fields):
            raise ValueError("required_fields cannot contain blank names")
        if len(fields) != len(set(fields)):
            raise ValueError("required_fields must be unique")
        return fields

    @classmethod
    def from_json(cls, path: str | Path) -> "FactorPluginManifest":
        """Load and validate a manifest from a UTF-8 JSON file."""

        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))

    load_json = from_json

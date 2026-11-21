"""Pydantic schemas for the Governed AI Analytics Copilot."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SemanticFilter(BaseModel):
    """A single governed filter expression."""

    dimension: str
    operator: Literal["=", "!=", ">=", "<="] = "="
    value: str


class SemanticQueryPlan(BaseModel):
    """Structured query plan emitted by the AI planner (never raw SQL)."""

    metrics: list[str] = Field(..., min_length=1, max_length=12)
    dimensions: list[str] = Field(default_factory=list, max_length=4)
    filters: list[SemanticFilter] = Field(default_factory=list)
    time_grain: Literal["day", "week", "month"] | None = None
    order_by: str | None = None
    order_descending: bool = True
    limit: int = Field(default=50, ge=1, le=500)


class GuardrailResult(BaseModel):
    """Result of security and semantic governance validation."""

    allowed: bool
    reason: str = ""
    category: Literal["ok", "prompt_injection", "sql_injection", "catalog_violation"] = "ok"


class MetricLineageInfo(BaseModel):
    """Governance metadata surfaced alongside every AI answer."""

    name: str
    label: str
    type: str
    description: str
    sql_formula: str


class CopilotResponse(BaseModel):
    """Full auditable response from the Governed AI Analytics Copilot."""

    question: str
    status: Literal["ok", "blocked", "out_of_scope"]
    provider: str
    plan: SemanticQueryPlan | None = None
    compiled_sql: str | None = None
    dialect: str | None = None
    metric_definitions: list[MetricLineageInfo] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    narrative: str
    execution_ms: float = 0.0

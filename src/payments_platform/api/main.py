"""FastAPI application exposing governed semantic metrics and the AI Copilot."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from payments_platform import __version__
from payments_platform.ai.copilot import GovernedAICopilot
from payments_platform.ai.guardrails import validate_query_plan
from payments_platform.ai.models import CopilotResponse, SemanticQueryPlan
from payments_platform.config import get_settings
from payments_platform.logging_config import configure_logging
from payments_platform.semantic.catalog import SemanticCatalog
from payments_platform.semantic.engine import SemanticQueryEngine

settings = get_settings()
configure_logging(settings.log_level)

app = FastAPI(
    title="Payments Semantic AI Platform API",
    description=(
        "Governed Semantic Layer & AI Analytics Copilot for FinTech Payments "
        "(dbt + MetricFlow + Gemini Vertex AI + DuckDB/BigQuery)."
    ),
    version=__version__,
)


class AskRequest(BaseModel):
    """Natural language analytics question."""

    question: str = Field(..., min_length=3, max_length=500)


def _build_services() -> tuple[SemanticCatalog, SemanticQueryEngine, GovernedAICopilot]:
    cfg = get_settings()
    catalog = SemanticCatalog.from_yaml(cfg.semantic_catalog_path)
    engine = SemanticQueryEngine(catalog=catalog, settings=cfg)
    copilot = GovernedAICopilot(catalog=catalog, engine=engine, settings=cfg)
    return catalog, engine, copilot


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness and configuration health endpoint for Cloud Run."""
    cfg = get_settings()
    return {
        "status": "healthy",
        "version": __version__,
        "app_env": cfg.app_env,
        "ai_provider": cfg.ai_provider,
    }


@app.get("/metrics/catalog")
def get_catalog() -> dict[str, object]:
    """Return the full governed Semantic Layer catalog (metrics & dimensions)."""
    catalog, _, _ = _build_services()
    return catalog.model_dump()


@app.post("/metrics/query")
def query_metrics(plan: SemanticQueryPlan) -> dict[str, object]:
    """Execute a structured SemanticQueryPlan directly against DuckDB or BigQuery."""
    catalog, engine, _ = _build_services()
    check = validate_query_plan(plan, catalog)
    if not check.allowed:
        raise HTTPException(status_code=400, detail=check.reason)
    result = engine.execute(plan)
    return {
        "dialect": result.dialect,
        "compiled_sql": result.compiled_sql,
        "row_count": result.row_count,
        "execution_ms": result.execution_ms,
        "rows": result.rows,
    }


@app.post("/copilot/ask", response_model=CopilotResponse)
def ask_copilot(payload: AskRequest) -> CopilotResponse:
    """Answer a natural language business question strictly via the governed Semantic Layer."""
    _, _, copilot = _build_services()
    return copilot.ask(payload.question)

"""Security and Semantic Governance Guardrails for the AI Copilot."""

from __future__ import annotations

import re

from payments_platform.ai.models import GuardrailResult, SemanticQueryPlan
from payments_platform.semantic.catalog import SemanticCatalog

PROMPT_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions", re.IGNORECASE),
    re.compile(r"system\s+prompt", re.IGNORECASE),
    re.compile(r"reveal\s+(your\s+)?(instructions|secrets|credentials|api\s*key)", re.IGNORECASE),
    re.compile(r"bypass\s+(guardrails|governance|semantic)", re.IGNORECASE),
]

SQL_INJECTION_PATTERNS = [
    re.compile(r"\b(drop|delete|truncate|alter|insert|update)\s+(table|database|schema)\b", re.I),
    re.compile(r"\bunion\s+select\b", re.IGNORECASE),
    re.compile(r";\s*(select|drop|delete)\b", re.IGNORECASE),
    re.compile(r"--\s*$"),
]


def inspect_user_question(question: str) -> GuardrailResult:
    """Detect prompt injection or raw SQL injection attempts before planning."""
    cleaned = question.strip()
    if not cleaned:
        return GuardrailResult(
            allowed=False,
            reason="Question cannot be empty.",
            category="catalog_violation",
        )

    for pattern in PROMPT_INJECTION_PATTERNS:
        if pattern.search(cleaned):
            return GuardrailResult(
                allowed=False,
                reason=(
                    "Request blocked by security guardrail: detected prompt-injection attempt. "
                    "Ask a business question about governed payment metrics."
                ),
                category="prompt_injection",
            )

    for pattern in SQL_INJECTION_PATTERNS:
        if pattern.search(cleaned):
            return GuardrailResult(
                allowed=False,
                reason=(
                    "Request blocked by security guardrail: raw SQL or destructive statements "
                    "are not permitted. All queries compile strictly through the Semantic Layer."
                ),
                category="sql_injection",
            )

    return GuardrailResult(allowed=True)


def validate_query_plan(plan: SemanticQueryPlan, catalog: SemanticCatalog) -> GuardrailResult:
    """Ensure every metric, dimension, and filter strictly belongs to the governed catalog."""
    unknown_metrics = [m for m in plan.metrics if m not in catalog.metrics]
    if unknown_metrics:
        return GuardrailResult(
            allowed=False,
            reason=(
                f"Ungoverned metrics requested: {unknown_metrics}. "
                f"Available metrics: {sorted(catalog.metrics.keys())}"
            ),
            category="catalog_violation",
        )

    unknown_dims = [d for d in plan.dimensions if d not in catalog.dimensions]
    if unknown_dims:
        return GuardrailResult(
            allowed=False,
            reason=(
                f"Ungoverned dimensions requested: {unknown_dims}. "
                f"Available dimensions: {sorted(catalog.dimensions.keys())}"
            ),
            category="catalog_violation",
        )

    for filt in plan.filters:
        if filt.dimension not in catalog.dimensions:
            return GuardrailResult(
                allowed=False,
                reason=f"Ungoverned filter dimension: '{filt.dimension}'.",
                category="catalog_violation",
            )
        dim_spec = catalog.dimensions[filt.dimension]
        if dim_spec.allowed_values and filt.value not in dim_spec.allowed_values:
            return GuardrailResult(
                allowed=False,
                reason=(
                    f"Invalid filter value '{filt.value}' for '{filt.dimension}'. "
                    f"Allowed values: {dim_spec.allowed_values}"
                ),
                category="catalog_violation",
            )

    return GuardrailResult(allowed=True)

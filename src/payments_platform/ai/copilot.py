"""Governed AI Analytics Copilot: Gemini (Vertex AI) + Deterministic Fallback Planner."""

from __future__ import annotations

import json
import logging
import unicodedata
from typing import Any

from payments_platform.ai.guardrails import inspect_user_question, validate_query_plan
from payments_platform.ai.models import (
    CopilotResponse,
    MetricLineageInfo,
    SemanticFilter,
    SemanticQueryPlan,
)
from payments_platform.config import Settings
from payments_platform.semantic.catalog import SemanticCatalog
from payments_platform.semantic.engine import SemanticQueryEngine

logger = logging.getLogger(__name__)


def _normalize(text: str) -> str:
    """Lowercase and strip accents for resilient bilingual (PT/EN) intent matching."""
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


class GovernedAICopilot:
    """Translates natural language into governed Semantic Layer queries (never raw SQL)."""

    def __init__(
        self,
        catalog: SemanticCatalog,
        engine: SemanticQueryEngine,
        settings: Settings,
    ) -> None:
        self.catalog = catalog
        self.engine = engine
        self.settings = settings

    def _plan_with_gemini(self, question: str) -> SemanticQueryPlan | None:
        """Use Google GenAI SDK (Vertex AI ADC or Gemini API) with structured JSON output."""
        from google import genai
        from google.genai import types

        if self.settings.ai_provider == "vertex_ai":
            client = genai.Client(
                vertexai=True,
                project=self.settings.gcp_project_id,
                location=self.settings.gcp_region,
            )
        else:
            client = genai.Client(api_key=self.settings.gemini_api_key)

        system_instruction = (
            "You are a Staff Analytics Engineering Semantic Planner for a FinTech Payments app. "
            "Translate the user's question into a valid JSON SemanticQueryPlan using ONLY the "
            "governed metrics, dimensions, and allowed filter values listed below. "
            "NEVER invent metric names, NEVER output SQL.\n\n"
            f"{self.catalog.to_llm_context()}"
        )

        response = client.models.generate_content(
            model=self.settings.gemini_model,
            contents=question,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                response_schema=SemanticQueryPlan,
                temperature=0.0,
            ),
        )
        if not response.text:
            return None
        payload = json.loads(response.text)
        return SemanticQueryPlan.model_validate(payload)

    def _plan_deterministic(self, question: str) -> SemanticQueryPlan | None:
        """Deterministic bilingual (PT/EN) semantic planner for $0 offline dev & CI evals."""
        q = _normalize(question)

        # 1. Detect requested governed metrics via synonyms
        matched_metrics: list[str] = []
        # Check more specific ratio metrics before broad terms
        ordered_metric_names = [
            "net_take_rate_bps",
            "chargeback_rate_bps",
            "approval_rate",
            "avg_ticket_brl",
            "chargeback_loss_brl",
            "net_revenue_brl",
            "mdr_revenue_brl",
            "net_settlement_brl",
            "gross_tpv_brl",
            "transaction_count",
        ]
        for m_name in ordered_metric_names:
            spec = self.catalog.metrics[m_name]
            tokens = [m_name, _normalize(spec.label), *(_normalize(s) for s in spec.synonyms)]
            if any(tok in q for tok in tokens):
                matched_metrics.append(m_name)

        if not matched_metrics:
            return None

        # Always include gross_tpv_brl as context when analyzing take-rate or chargeback rate
        if (
            any(m in matched_metrics for m in ("net_take_rate_bps", "chargeback_rate_bps"))
            and "gross_tpv_brl" not in matched_metrics
        ):
            matched_metrics.append("gross_tpv_brl")

        # 2. Detect dimensions (group by)
        dimensions: list[str] = []
        dim_keywords = {
            "region": ["regiao", "region", "regioes", "estado"],
            "mcc_category": ["mcc", "categoria", "category", "segmento de negocio", "vertical"],
            "merchant_tier": ["tier", "porte", "smb", "enterprise", "mid-market"],
            "payment_method": ["metodo", "meio de pagamento", "payment method", "pix", "cartao"],
            "card_brand": ["bandeira", "brand", "visa", "mastercard", "elo"],
        }
        for dim_name, keywords in dim_keywords.items():
            if any(kw in q for kw in keywords):
                dimensions.append(dim_name)

        time_grain: str | None = None
        if any(kw in q for kw in ["mensal", "por mes", "monthly", "mes a mes", "evolucao"]):
            dimensions.append("transaction_date")
            time_grain = "month"
        elif any(kw in q for kw in ["semanal", "por semana", "weekly"]):
            dimensions.append("transaction_date")
            time_grain = "week"
        elif any(kw in q for kw in ["diario", "por dia", "daily"]):
            dimensions.append("transaction_date")
            time_grain = "day"

        # 3. Detect explicit categorical filters from allowed values
        filters: list[SemanticFilter] = []
        for dim_name, dim_spec in self.catalog.dimensions.items():
            for allowed_val in dim_spec.allowed_values:
                norm_val = _normalize(allowed_val)
                if f" {norm_val}" in f" {q}" and norm_val not in {"sul"}:
                    filters.append(
                        SemanticFilter(dimension=dim_name, operator="=", value=allowed_val)
                    )
                elif norm_val == "sul" and ("regiao sul" in q or "no sul" in q or "do sul" in q):
                    filters.append(SemanticFilter(dimension=dim_name, operator="=", value="Sul"))

        # Avoid grouping by a dimension that is already filtered to a single value unless requested
        filtered_dims = {f.dimension for f in filters}
        dimensions = [d for d in dimensions if d not in filtered_dims]

        order_by = "transaction_date" if "transaction_date" in dimensions else matched_metrics[0]
        order_desc = order_by != "transaction_date"

        return SemanticQueryPlan(
            metrics=matched_metrics[:4],
            dimensions=dimensions[:3],
            filters=filters,
            time_grain=time_grain,
            order_by=order_by,
            order_descending=order_desc,
            limit=50,
        )

    def _build_narrative(
        self,
        plan: SemanticQueryPlan,
        rows: list[dict[str, Any]],
    ) -> str:
        """Produce a grounded executive summary strictly from returned semantic rows."""
        if not rows:
            return "Nenhum registro encontrado para os filtros informados na camada semântica."

        primary_metric = plan.metrics[0]
        m_spec = self.catalog.metrics[primary_metric]
        top_row = rows[0]

        def _fmt(metric_name: str, val: Any) -> str:
            if val is None:
                return "N/A"
            fmt = self.catalog.metrics[metric_name].format
            num = float(val)
            if fmt == "currency_brl":
                return f"R$ {num:,.2f}"
            if fmt == "percentage":
                return f"{num * 100:.2f}%"
            if fmt == "bps":
                return f"{num:.1f} bps ({num / 100:.2f}%)"
            return f"{int(round(num)):,}"

        if not plan.dimensions:
            summary_bits = [
                f"**{self.catalog.metrics[m].label}**: {_fmt(m, top_row.get(m))}"
                for m in plan.metrics
            ]
            return "Resultado consolidado governado: " + " | ".join(summary_bits) + "."

        dim_label = ", ".join(f"{d}={top_row.get(d)}" for d in plan.dimensions)
        lead_val = _fmt(primary_metric, top_row.get(primary_metric))
        narrative = (
            f"Foram retornados **{len(rows)}** grupos governados. "
            f"O destaque em **{m_spec.label}** é **{dim_label}** com **{lead_val}**."
        )
        if "chargeback_rate_bps" in plan.metrics:
            cb_val = float(top_row.get("chargeback_rate_bps") or 0.0)
            if cb_val > 100.0:
                narrative += (
                    f" Alerta de Risco: `{dim_label}` está acima do limiar de bandeira "
                    f"(100 bps), registrando **{cb_val:.1f} bps**."
                )
        return narrative

    def ask(self, question: str) -> CopilotResponse:
        """Answer a natural language analytics question strictly via the Semantic Layer."""
        input_check = inspect_user_question(question)
        if not input_check.allowed:
            return CopilotResponse(
                question=question,
                status="blocked",
                provider=self.settings.ai_provider,
                narrative=input_check.reason,
            )

        plan: SemanticQueryPlan | None
        provider_used = self.settings.ai_provider
        if self.settings.ai_provider in {"vertex_ai", "gemini_api"}:
            try:
                plan = self._plan_with_gemini(question)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Gemini planner unavailable (%s); falling back to deterministic planner.",
                    exc,
                )
                plan = self._plan_deterministic(question)
                provider_used = "deterministic_fallback"
        else:
            plan = self._plan_deterministic(question)

        if plan is None:
            available = ", ".join(sorted(self.catalog.metrics.keys()))
            return CopilotResponse(
                question=question,
                status="out_of_scope",
                provider=provider_used,
                narrative=(
                    "Não identifiquei uma métrica governada correspondente à sua pergunta. "
                    f"Métricas oficiais disponíveis no catálogo semântico: {available}."
                ),
            )

        plan_check = validate_query_plan(plan, self.catalog)
        if not plan_check.allowed:
            return CopilotResponse(
                question=question,
                status="blocked",
                provider=provider_used,
                plan=plan,
                narrative=plan_check.reason,
            )

        result = self.engine.execute(plan)
        lineage = [
            MetricLineageInfo(
                name=m,
                label=self.catalog.metrics[m].label,
                type=self.catalog.metrics[m].type,
                description=self.catalog.metrics[m].description,
                sql_formula=self.catalog.metrics[m].sql_expr,
            )
            for m in plan.metrics
        ]
        narrative = self._build_narrative(plan, result.rows)

        return CopilotResponse(
            question=question,
            status="ok",
            provider=provider_used,
            plan=plan,
            compiled_sql=result.compiled_sql,
            dialect=result.dialect,
            metric_definitions=lineage,
            rows=result.rows,
            narrative=narrative,
            execution_ms=result.execution_ms,
        )

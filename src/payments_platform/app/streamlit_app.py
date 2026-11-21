"""Executive BI & Governed AI Analytics Copilot UI (Streamlit)."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from payments_platform.ai.copilot import GovernedAICopilot
from payments_platform.ai.models import SemanticQueryPlan
from payments_platform.config import get_settings
from payments_platform.semantic.catalog import SemanticCatalog
from payments_platform.semantic.engine import SemanticQueryEngine

st.set_page_config(
    page_title="Payments Semantic AI Copilot",
    page_icon="💳",
    layout="wide",
)

settings = get_settings()
catalog = SemanticCatalog.from_yaml(settings.semantic_catalog_path)
engine = SemanticQueryEngine(catalog=catalog, settings=settings)
copilot = GovernedAICopilot(catalog=catalog, engine=engine, settings=settings)

st.title("Payments Semantic AI Platform")
st.caption(
    f"Governed Semantic Layer (dbt + MetricFlow) + AI Copilot | "
    f"Engine: `{settings.app_env.upper()}` | AI Provider: `{settings.ai_provider}`"
)

# Executive KPI Banner (always queried through the governed Semantic Layer)
kpi_result = engine.execute(
    SemanticQueryPlan(
        metrics=[
            "gross_tpv_brl",
            "net_revenue_brl",
            "net_take_rate_bps",
            "approval_rate",
            "chargeback_rate_bps",
        ],
        limit=1,
    )
)
if kpi_result.rows:
    kpi = kpi_result.rows[0]
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Gross TPV", f"R$ {kpi['gross_tpv_brl']:,.0f}")
    c2.metric("Net Revenue", f"R$ {kpi['net_revenue_brl']:,.0f}")
    c3.metric("Net Take-Rate", f"{kpi['net_take_rate_bps']:.1f} bps")
    c4.metric("Approval Rate", f"{kpi['approval_rate'] * 100:.2f}%")
    c5.metric("Chargeback Rate", f"{kpi['chargeback_rate_bps']:.1f} bps")

st.divider()

tab_ai, tab_catalog = st.tabs(["Governed AI Copilot", "Semantic Metric Catalog"])

with tab_ai:
    st.subheader("Pergunte em linguagem natural (0% alucinação de fórmula)")
    examples = [
        "Qual o chargeback rate por categoria MCC?",
        "Mostre o net take rate e gross TPV por regiao",
        "Evolucao mensal de gross TPV e taxa de aprovacao",
        "Qual o ticket medio por metodo de pagamento?",
    ]
    selected_example = st.selectbox("Exemplos rápidos:", [""] + examples)
    question = st.text_input(
        "Sua pergunta de negócio:",
        value=selected_example,
        placeholder="Ex.: Qual o chargeback rate e TPV por MCC?",
    )

    if st.button("Consultar Camada Semântica", type="primary") and question.strip():
        response = copilot.ask(question)
        if response.status != "ok":
            st.warning(response.narrative)
        else:
            st.success(response.narrative)
            df = pd.DataFrame(response.rows)
            st.dataframe(df, use_container_width=True)

            if response.plan and response.plan.dimensions and not df.empty:
                x_col = response.plan.dimensions[0]
                y_col = response.plan.metrics[0]
                fig = (
                    px.line(df, x=x_col, y=y_col, markers=True, title=f"{y_col} por {x_col}")
                    if x_col == "transaction_date"
                    else px.bar(df, x=x_col, y=y_col, title=f"{y_col} por {x_col}")
                )
                st.plotly_chart(fig, use_container_width=True)

            with st.expander("Auditoria: SQL Compilado & Lineage das Métricas"):
                st.code(response.compiled_sql or "", language="sql")
                for m in response.metric_definitions:
                    st.markdown(f"- **{m.label}** (`{m.name}`): {m.description}")

with tab_catalog:
    st.subheader("Catálogo Semântico Oficial (`contracts/semantic_catalog.yaml`)")
    catalog_rows = [
        {
            "Metric": m.name,
            "Label": m.label,
            "Type": m.type,
            "Format": m.format,
            "Description": m.description,
        }
        for m in catalog.metrics.values()
    ]
    st.dataframe(pd.DataFrame(catalog_rows), use_container_width=True)

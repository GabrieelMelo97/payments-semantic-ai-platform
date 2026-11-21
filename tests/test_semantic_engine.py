"""Tests for Governed Semantic Catalog sync, SQL compilation, and ratio math accuracy."""

from __future__ import annotations

import yaml

from payments_platform.ai.models import SemanticFilter, SemanticQueryPlan
from payments_platform.config import Settings
from payments_platform.semantic.catalog import SemanticCatalog
from payments_platform.semantic.engine import SemanticQueryEngine


def test_semantic_catalog_stays_in_sync_with_dbt_metricflow(e2e_settings: Settings) -> None:
    """Ensure semantic_catalog.yaml and dbt _semantic_models.yml define identical metrics."""
    catalog = SemanticCatalog.from_yaml(e2e_settings.semantic_catalog_path)
    dbt_sem_path = (
        e2e_settings.project_root / "dbt_project" / "models" / "marts" / "_semantic_models.yml"
    )
    with dbt_sem_path.open("r", encoding="utf-8") as fh:
        dbt_sem = yaml.safe_load(fh)

    dbt_metric_names = {m["name"] for m in dbt_sem["metrics"]}
    catalog_metric_names = set(catalog.metrics.keys())
    assert catalog_metric_names == dbt_metric_names


def test_semantic_engine_executes_governed_ratios_on_duckdb(e2e_settings: Settings) -> None:
    catalog = SemanticCatalog.from_yaml(e2e_settings.semantic_catalog_path)
    engine = SemanticQueryEngine(catalog=catalog, settings=e2e_settings)

    plan = SemanticQueryPlan(
        metrics=[
            "gross_tpv_brl",
            "net_revenue_brl",
            "net_take_rate_bps",
            "approval_rate",
            "chargeback_rate_bps",
        ],
        dimensions=["region"],
        order_by="gross_tpv_brl",
    )
    res = engine.execute(plan)

    assert res.dialect == "duckdb"
    assert res.row_count > 0
    for row in res.rows:
        assert row["gross_tpv_brl"] >= 0
        assert 0.0 <= row["approval_rate"] <= 1.0
        assert row["chargeback_rate_bps"] >= 0.0
        # Verify exact ratio consistency (no average-of-averages bug)
        if row["gross_tpv_brl"] > 0:
            expected_bps = round((row["net_revenue_brl"] / row["gross_tpv_brl"]) * 10000.0, 2)
            assert abs(row["net_take_rate_bps"] - expected_bps) < 0.2


def test_semantic_engine_compiles_bigquery_dialect_safely(e2e_settings: Settings) -> None:
    catalog = SemanticCatalog.from_yaml(e2e_settings.semantic_catalog_path)
    bq_settings = e2e_settings.model_copy(
        update={
            "app_env": "gcp",
            "gcp_project_id": "demo-project",
            "bq_dataset_marts": "payments_marts",
        }
    )
    engine = SemanticQueryEngine(catalog=catalog, settings=bq_settings)

    plan = SemanticQueryPlan(
        metrics=["gross_tpv_brl", "net_take_rate_bps"],
        dimensions=["transaction_date"],
        time_grain="month",
        filters=[SemanticFilter(dimension="region", operator="=", value="Sul")],
    )
    compiled = engine.compile(plan, dialect="bigquery")

    assert "`demo-project.payments_marts.fct_payments`" in compiled.sql
    assert "date_trunc(transaction_date, month)" in compiled.sql
    assert "region = 'Sul'" in compiled.sql

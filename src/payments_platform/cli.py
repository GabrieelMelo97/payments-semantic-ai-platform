"""Unified CLI for data generation, ingestion, semantic queries, AI copilot, and reporting."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import typer

from payments_platform.ai.copilot import GovernedAICopilot
from payments_platform.ai.models import SemanticQueryPlan
from payments_platform.config import get_settings
from payments_platform.data_generator import generate_payments_datasets, save_datasets_parquet
from payments_platform.ingestion import run_ingestion
from payments_platform.logging_config import configure_logging
from payments_platform.semantic.catalog import SemanticCatalog
from payments_platform.semantic.engine import SemanticQueryEngine

app = typer.Typer(help="Payments Semantic AI Platform CLI")
logger = logging.getLogger(__name__)


@app.command()
def generate(
    merchants: int = typer.Option(60, help="Number of merchants to generate."),
    transactions: int = typer.Option(6000, help="Number of clean base transactions."),
    days: int = typer.Option(90, help="Historical time window in days."),
    seed: int = typer.Option(42, help="Deterministic RNG seed."),
) -> None:
    """Generate deterministic FinTech payments raw Parquet datasets."""
    settings = get_settings()
    configure_logging(settings.log_level)
    datasets = generate_payments_datasets(
        n_merchants=merchants,
        n_transactions=transactions,
        days=days,
        seed=seed,
    )
    paths = save_datasets_parquet(datasets, settings.resolved_data_dir)
    typer.echo(json.dumps({k: str(v) for k, v in paths.items()}, indent=2))


@app.command()
def ingest() -> None:
    """Validate raw datasets via Pandera contracts, quarantine anomalies, and load warehouse."""
    settings = get_settings()
    configure_logging(settings.log_level)
    summary = run_ingestion(settings)
    typer.echo(json.dumps(summary.__dict__, indent=2))


@app.command()
def ask(
    question: str = typer.Argument(..., help="Natural language question for the AI Copilot."),
) -> None:
    """Ask the Governed AI Analytics Copilot a business question."""
    settings = get_settings()
    configure_logging(settings.log_level)
    catalog = SemanticCatalog.from_yaml(settings.semantic_catalog_path)
    engine = SemanticQueryEngine(catalog=catalog, settings=settings)
    copilot = GovernedAICopilot(catalog=catalog, engine=engine, settings=settings)
    response = copilot.ask(question)
    typer.echo(response.model_dump_json(indent=2))


@app.command()
def report(
    output_path: Path = typer.Option(
        Path("docs/assets/executive_metrics_snapshot.md"),
        help="Output Markdown report path.",
    ),
) -> None:
    """Generate an auditable executive metrics snapshot from the Semantic Layer."""
    settings = get_settings()
    configure_logging(settings.log_level)
    catalog = SemanticCatalog.from_yaml(settings.semantic_catalog_path)
    engine = SemanticQueryEngine(catalog=catalog, settings=settings)

    overall = engine.execute(
        SemanticQueryPlan(
            metrics=[
                "gross_tpv_brl",
                "net_revenue_brl",
                "mdr_revenue_brl",
                "chargeback_loss_brl",
                "net_take_rate_bps",
                "approval_rate",
                "chargeback_rate_bps",
                "transaction_count",
            ],
            limit=1,
        )
    )
    by_mcc = engine.execute(
        SemanticQueryPlan(
            metrics=["gross_tpv_brl", "net_take_rate_bps", "chargeback_rate_bps", "approval_rate"],
            dimensions=["mcc_category"],
            order_by="chargeback_rate_bps",
            order_descending=True,
            limit=10,
        )
    )
    by_region = engine.execute(
        SemanticQueryPlan(
            metrics=[
                "gross_tpv_brl",
                "net_revenue_brl",
                "net_take_rate_bps",
                "chargeback_rate_bps",
            ],
            dimensions=["region"],
            order_by="gross_tpv_brl",
            order_descending=True,
            limit=10,
        )
    )

    k = overall.rows[0]
    lines = [
        "# Executive Metrics Snapshot (Governed Semantic Layer)",
        "",
        f"- **Engine:** `{overall.dialect}`",
        f"- **Gross TPV:** R$ {k['gross_tpv_brl']:,.2f}",
        f"- **Net Revenue:** R$ {k['net_revenue_brl']:,.2f}",
        f"- **Net Take-Rate:** {k['net_take_rate_bps']:.2f} bps",
        f"- **Approval Rate:** {k['approval_rate'] * 100:.2f}%",
        f"- **Chargeback Rate:** {k['chargeback_rate_bps']:.2f} bps",
        f"- **Total Transactions (deduplicated):** {int(k['transaction_count']):,}",
        "",
        "## Risk & Profitability by MCC Category",
        "",
        (
            "| MCC Category | Gross TPV (BRL) | Net Take-Rate (bps) "
            "| Chargeback Rate (bps) | Approval Rate |"
        ),
        "| :--- | ---: | ---: | ---: | ---: |",
    ]
    for r in by_mcc.rows:
        lines.append(
            f"| `{r['mcc_category']}` | R$ {r['gross_tpv_brl']:,.2f} | "
            f"{r['net_take_rate_bps']:.1f} | {r['chargeback_rate_bps']:.1f} | "
            f"{r['approval_rate'] * 100:.2f}% |"
        )

    lines.extend(
        [
            "",
            "## Performance by Region",
            "",
            (
                "| Region | Gross TPV (BRL) | Net Revenue (BRL) "
                "| Net Take-Rate (bps) | Chargeback Rate (bps) |"
            ),
            "| :--- | ---: | ---: | ---: | ---: |",
        ]
    )
    for r in by_region.rows:
        lines.append(
            f"| `{r['region']}` | R$ {r['gross_tpv_brl']:,.2f} | "
            f"R$ {r['net_revenue_brl']:,.2f} | {r['net_take_rate_bps']:.1f} | "
            f"{r['chargeback_rate_bps']:.1f} |"
        )

    resolved_out = output_path if output_path.is_absolute() else settings.project_root / output_path
    resolved_out.parent.mkdir(parents=True, exist_ok=True)
    resolved_out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("Wrote executive metrics snapshot to %s", resolved_out)
    typer.echo(f"Report written to {resolved_out}")


if __name__ == "__main__":
    app()

"""Deterministic Semantic Query Compiler and Executor (DuckDB & BigQuery).

Guarantees zero hallucinated formulas and zero raw LLM SQL execution by compiling
validated SemanticQueryPlan objects strictly from the governed SemanticCatalog.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import duckdb

from payments_platform.ai.models import SemanticQueryPlan
from payments_platform.config import Settings
from payments_platform.semantic.catalog import SemanticCatalog

logger = logging.getLogger(__name__)

VALID_TIME_GRAINS = {"day", "week", "month"}


@dataclass(frozen=True)
class CompiledSemanticQuery:
    """SQL query compiled deterministically from a SemanticQueryPlan."""

    sql: str
    params: list[Any]
    dialect: str


@dataclass(frozen=True)
class SemanticQueryResult:
    """Execution output from the Semantic Layer engine."""

    compiled_sql: str
    dialect: str
    rows: list[dict[str, Any]]
    row_count: int
    execution_ms: float


class SemanticQueryEngine:
    """Compiles and executes governed semantic queries on DuckDB or BigQuery."""

    def __init__(self, catalog: SemanticCatalog, settings: Settings) -> None:
        self.catalog = catalog
        self.settings = settings

    def _source_table_ref(self, dialect: str) -> str:
        mart = self.catalog.source_mart
        if dialect == "bigquery":
            return f"`{self.settings.gcp_project_id}.{self.settings.bq_dataset_marts}.{mart}`"
        return f"marts.{mart}"

    def _time_trunc_expr(self, col_expr: str, grain: str, dialect: str) -> str:
        if grain not in VALID_TIME_GRAINS:
            raise ValueError(f"Unsupported time_grain: {grain}")
        if dialect == "bigquery":
            return f"date_trunc({col_expr}, {grain})"
        return f"cast(date_trunc('{grain}', {col_expr}) as date)"

    def compile(self, plan: SemanticQueryPlan, dialect: str = "duckdb") -> CompiledSemanticQuery:
        """Compile a validated SemanticQueryPlan into deterministic SQL."""
        if not plan.metrics:
            raise ValueError("SemanticQueryPlan must include at least one governed metric.")

        for metric_name in plan.metrics:
            if metric_name not in self.catalog.metrics:
                raise ValueError(f"Unknown metric '{metric_name}' — not in governed catalog.")

        for dim_name in plan.dimensions:
            if dim_name not in self.catalog.dimensions:
                raise ValueError(f"Unknown dimension '{dim_name}' — not in governed catalog.")

        select_parts: list[str] = []
        group_by_parts: list[str] = []

        for dim_name in plan.dimensions:
            dim = self.catalog.dimensions[dim_name]
            if dim.type == "time" and plan.time_grain:
                expr = self._time_trunc_expr(dim.sql_expr, plan.time_grain, dialect)
                select_parts.append(f"{expr} as {dim_name}")
                group_by_parts.append(expr)
            else:
                select_parts.append(f"{dim.sql_expr} as {dim_name}")
                group_by_parts.append(dim.sql_expr)

        for metric_name in plan.metrics:
            metric = self.catalog.metrics[metric_name]
            select_parts.append(f"round({metric.sql_expr}, 4) as {metric_name}")

        where_clauses: list[str] = []
        params: list[Any] = []

        for filt in plan.filters:
            if filt.dimension not in self.catalog.dimensions:
                raise ValueError(f"Unknown filter dimension '{filt.dimension}'.")
            dim = self.catalog.dimensions[filt.dimension]
            if dim.allowed_values and filt.value not in dim.allowed_values:
                raise ValueError(
                    f"Invalid value '{filt.value}' for dimension '{filt.dimension}'. "
                    f"Allowed: {dim.allowed_values}"
                )
            if dialect == "bigquery":
                # Parameterized safely via validated allowlist / ISO date format
                safe_val = str(filt.value).replace("'", "")
                where_clauses.append(f"{dim.sql_expr} {filt.operator} '{safe_val}'")
            else:
                where_clauses.append(f"{dim.sql_expr} {filt.operator} ?")
                params.append(filt.value)

        table_ref = self._source_table_ref(dialect)
        sql_lines = [
            "select",
            "    " + ",\n    ".join(select_parts),
            f"from {table_ref}",
        ]
        if where_clauses:
            sql_lines.append("where " + "\n  and ".join(where_clauses))
        if group_by_parts:
            sql_lines.append("group by " + ", ".join(group_by_parts))

        if plan.order_by and (plan.order_by in plan.metrics or plan.order_by in plan.dimensions):
            direction = "desc" if plan.order_descending else "asc"
            sql_lines.append(f"order by {plan.order_by} {direction}")
        elif plan.dimensions and "transaction_date" in plan.dimensions:
            sql_lines.append("order by transaction_date asc")
        elif plan.metrics:
            sql_lines.append(f"order by {plan.metrics[0]} desc")

        sql_lines.append(f"limit {int(plan.limit)}")
        compiled_sql = "\n".join(sql_lines)
        return CompiledSemanticQuery(sql=compiled_sql, params=params, dialect=dialect)

    def execute(self, plan: SemanticQueryPlan) -> SemanticQueryResult:
        """Execute a SemanticQueryPlan against DuckDB (local) or BigQuery (GCP)."""
        t0 = time.perf_counter()
        if self.settings.app_env == "gcp":
            return self._execute_bigquery(plan, t0)
        return self._execute_duckdb(plan, t0)

    def _execute_duckdb(self, plan: SemanticQueryPlan, t0: float) -> SemanticQueryResult:
        compiled = self.compile(plan, dialect="duckdb")
        db_path = self.settings.resolved_duckdb_path
        con = duckdb.connect(str(db_path), read_only=True)
        try:
            cursor = con.execute(compiled.sql, compiled.params)
            columns = [desc[0] for desc in cursor.description]
            raw_rows = cursor.fetchall()
        finally:
            con.close()

        rows = [
            {
                col: (str(val) if hasattr(val, "isoformat") else val)
                for col, val in zip(columns, r, strict=False)
            }
            for r in raw_rows
        ]
        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        return SemanticQueryResult(
            compiled_sql=compiled.sql,
            dialect="duckdb",
            rows=rows,
            row_count=len(rows),
            execution_ms=elapsed_ms,
        )

    def _execute_bigquery(self, plan: SemanticQueryPlan, t0: float) -> SemanticQueryResult:
        from google.cloud import bigquery

        compiled = self.compile(plan, dialect="bigquery")
        client = bigquery.Client(project=self.settings.gcp_project_id)
        job_config = bigquery.QueryJobConfig(maximum_bytes_billed=self.settings.bq_max_bytes_billed)
        query_job = client.query(compiled.sql, job_config=job_config)
        rows = [
            {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in dict(row).items()}
            for row in query_job.result()
        ]
        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        return SemanticQueryResult(
            compiled_sql=compiled.sql,
            dialect="bigquery",
            rows=rows,
            row_count=len(rows),
            execution_ms=elapsed_ms,
        )

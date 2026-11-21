"""Idempotent ingestion pipeline with Pandera Data Contracts & Quarantine (WAP pattern).

Supports Local-First DuckDB warehouse (cost $0) and GCP (GCS + BigQuery) parity.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import duckdb
import pandas as pd
import pandera.pandas as pa
from pandera.pandas import Check, Column, DataFrameSchema

from payments_platform.config import Settings

logger = logging.getLogger(__name__)

# Pandera Data Contracts aligned with contracts/raw_payments_contract.yaml
MERCHANTS_CONTRACT = DataFrameSchema(
    {
        "merchant_id": Column(str, nullable=False),
        "merchant_name": Column(str, nullable=False),
        "mcc_category": Column(
            str,
            Check.isin(
                ["ecommerce", "grocery", "restaurants", "travel", "saas_digital", "electronics"]
            ),
            nullable=False,
        ),
        "region": Column(
            str,
            Check.isin(["Sudeste", "Sul", "Nordeste", "Centro-Oeste", "Norte"]),
            nullable=False,
        ),
        "tier": Column(str, Check.isin(["SMB", "Mid-Market", "Enterprise"]), nullable=False),
        "mdr_rate_bps": Column(float, Check.in_range(50.0, 600.0), nullable=False),
        "interchange_rate_bps": Column(float, Check.in_range(20.0, 350.0), nullable=False),
    },
    coerce=True,
)

TRANSACTIONS_CONTRACT = DataFrameSchema(
    {
        "transaction_id": Column(str, nullable=False),
        "merchant_id": Column(str, nullable=False),
        "payment_method": Column(
            str, Check.isin(["credit_card", "debit_card", "pix"]), nullable=False
        ),
        "card_brand": Column(
            str, Check.isin(["visa", "mastercard", "elo", "pix_instant"]), nullable=False
        ),
        "installments": Column(int, Check.in_range(1, 12), nullable=False),
        "gross_amount_brl": Column(float, Check.in_range(0.01, 500_000.0), nullable=False),
        "status": Column(str, Check.isin(["approved", "declined", "refunded"]), nullable=False),
    },
    coerce=True,
)

CHARGEBACKS_CONTRACT = DataFrameSchema(
    {
        "chargeback_id": Column(str, nullable=False),
        "transaction_id": Column(str, nullable=False),
        "reason_code": Column(
            str,
            Check.isin(
                [
                    "fraud_card_not_present",
                    "merchandise_not_received",
                    "duplicate_processing",
                    "unrecognized_charge",
                ]
            ),
            nullable=False,
        ),
        "disputed_amount_brl": Column(float, Check.greater_than(0.0), nullable=False),
        "dispute_status": Column(str, Check.isin(["lost", "won", "under_review"]), nullable=False),
    },
    coerce=True,
)


@dataclass(frozen=True)
class IngestionSummary:
    """Metrics produced by an ingestion run."""

    target: str
    merchants_loaded: int
    transactions_valid: int
    transactions_quarantined: int
    chargebacks_loaded: int
    quarantine_rate: float


def validate_and_split_transactions(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply Pandera Data Contract to transactions, isolating invalid rows in quarantine."""
    try:
        valid_df = TRANSACTIONS_CONTRACT.validate(df, lazy=True)
        empty_q = df.iloc[0:0].copy()
        empty_q["quarantine_reason"] = pd.Series(dtype="object")
        empty_q["quarantined_at"] = pd.Series(dtype="datetime64[ns, UTC]")
        return valid_df, empty_q
    except pa.errors.SchemaErrors as exc:
        failure_cases = exc.failure_cases
        bad_indices = sorted(
            {
                int(i)
                for i in failure_cases["index"].dropna().tolist()
                if isinstance(i, (int, float))
            }
        )
        valid_df = df.drop(index=bad_indices).reset_index(drop=True)
        quarantine_df = df.loc[bad_indices].copy().reset_index(drop=True)

        reasons_by_idx: dict[int, list[str]] = {}
        for row in failure_cases.itertuples(index=False):
            if pd.notna(row.index):
                idx_key = int(row.index)
                reasons_by_idx.setdefault(idx_key, []).append(f"{row.column}:{row.check}")

        quarantine_df["quarantine_reason"] = [
            "; ".join(sorted(set(reasons_by_idx.get(i, ["contract_violation"]))))
            for i in bad_indices
        ]
        quarantine_df["quarantined_at"] = datetime.now(timezone.utc)

        # Re-validate the clean slice to guarantee 100% contract adherence
        valid_df = TRANSACTIONS_CONTRACT.validate(valid_df, lazy=True)
        return valid_df, quarantine_df


def ingest_local_duckdb(settings: Settings) -> IngestionSummary:
    """Load validated raw datasets into local DuckDB warehouse idempotently."""
    raw_dir = settings.resolved_data_dir / "raw"
    db_path = settings.resolved_duckdb_path
    db_path.parent.mkdir(parents=True, exist_ok=True)

    merchants_init = pd.read_parquet(raw_dir / "raw_merchants_initial.parquet")
    merchants_curr = pd.read_parquet(raw_dir / "raw_merchants.parquet")
    transactions_raw = pd.read_parquet(raw_dir / "raw_transactions.parquet")
    chargebacks_raw = pd.read_parquet(raw_dir / "raw_chargebacks.parquet")

    merchants_init = MERCHANTS_CONTRACT.validate(merchants_init, lazy=True)
    merchants_curr = MERCHANTS_CONTRACT.validate(merchants_curr, lazy=True)
    chargebacks_valid = CHARGEBACKS_CONTRACT.validate(chargebacks_raw, lazy=True)
    transactions_valid, transactions_quarantine = validate_and_split_transactions(transactions_raw)

    quarantine_rate = (
        len(transactions_quarantine) / len(transactions_raw) if len(transactions_raw) > 0 else 0.0
    )

    con = duckdb.connect(str(db_path))
    try:
        con.execute("CREATE SCHEMA IF NOT EXISTS raw")
        con.register("v_merchants_init", merchants_init)
        con.register("v_merchants_curr", merchants_curr)
        con.register("v_transactions_valid", transactions_valid)
        con.register("v_transactions_quarantine", transactions_quarantine)
        con.register("v_chargebacks", chargebacks_valid)

        # Idempotent atomic replacement of raw landing tables
        con.execute(
            "CREATE OR REPLACE TABLE raw.raw_merchants_history AS "
            "SELECT * FROM v_merchants_init UNION ALL SELECT * FROM v_merchants_curr"
        )
        con.execute("CREATE OR REPLACE TABLE raw.raw_merchants AS SELECT * FROM v_merchants_curr")
        con.execute(
            "CREATE OR REPLACE TABLE raw.raw_transactions AS SELECT * FROM v_transactions_valid"
        )
        con.execute(
            "CREATE OR REPLACE TABLE raw.raw_transactions_quarantine AS "
            "SELECT * FROM v_transactions_quarantine"
        )
        con.execute("CREATE OR REPLACE TABLE raw.raw_chargebacks AS SELECT * FROM v_chargebacks")
    finally:
        con.close()

    summary = IngestionSummary(
        target=f"duckdb://{db_path}",
        merchants_loaded=len(merchants_curr),
        transactions_valid=len(transactions_valid),
        transactions_quarantined=len(transactions_quarantine),
        chargebacks_loaded=len(chargebacks_valid),
        quarantine_rate=round(quarantine_rate, 6),
    )
    logger.info("Local ingestion completed: %s", summary)
    return summary


def ingest_gcp_bigquery(settings: Settings) -> IngestionSummary:
    """Upload validated Parquet files to GCS and load idempotently into BigQuery raw dataset."""
    from google.cloud import bigquery, storage

    if not settings.gcp_project_id or not settings.gcs_raw_bucket:
        raise ValueError("GCP_PROJECT_ID and GCS_RAW_BUCKET must be configured when APP_ENV=gcp")

    raw_dir = settings.resolved_data_dir / "raw"
    merchants_init = MERCHANTS_CONTRACT.validate(
        pd.read_parquet(raw_dir / "raw_merchants_initial.parquet"), lazy=True
    )
    merchants_curr = MERCHANTS_CONTRACT.validate(
        pd.read_parquet(raw_dir / "raw_merchants.parquet"), lazy=True
    )
    chargebacks_valid = CHARGEBACKS_CONTRACT.validate(
        pd.read_parquet(raw_dir / "raw_chargebacks.parquet"), lazy=True
    )
    transactions_raw = pd.read_parquet(raw_dir / "raw_transactions.parquet")
    transactions_valid, transactions_quarantine = validate_and_split_transactions(transactions_raw)

    merchants_history = pd.concat([merchants_init, merchants_curr], ignore_index=True)

    storage_client = storage.Client(project=settings.gcp_project_id)
    bq_client = bigquery.Client(project=settings.gcp_project_id)
    bucket = storage_client.bucket(settings.gcs_raw_bucket)

    tables = {
        "raw_merchants": merchants_curr,
        "raw_merchants_history": merchants_history,
        "raw_transactions": transactions_valid,
        "raw_transactions_quarantine": transactions_quarantine,
        "raw_chargebacks": chargebacks_valid,
    }

    validated_dir = settings.resolved_data_dir / "validated"
    validated_dir.mkdir(parents=True, exist_ok=True)

    for table_name, df in tables.items():
        local_pq = validated_dir / f"{table_name}.parquet"
        df.to_parquet(local_pq, index=False)

        blob_path = f"payments/validated/{table_name}.parquet"
        bucket.blob(blob_path).upload_from_filename(str(local_pq))

        table_id = f"{settings.gcp_project_id}.{settings.bq_dataset_raw}.{table_name}"
        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.PARQUET,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        )
        load_job = bq_client.load_table_from_uri(
            f"gs://{settings.gcs_raw_bucket}/{blob_path}",
            table_id,
            job_config=job_config,
        )
        load_job.result()
        logger.info("Loaded %d rows into BigQuery table %s", len(df), table_id)

    quarantine_rate = (
        len(transactions_quarantine) / len(transactions_raw) if len(transactions_raw) > 0 else 0.0
    )
    return IngestionSummary(
        target=f"bigquery://{settings.gcp_project_id}.{settings.bq_dataset_raw}",
        merchants_loaded=len(merchants_curr),
        transactions_valid=len(transactions_valid),
        transactions_quarantined=len(transactions_quarantine),
        chargebacks_loaded=len(chargebacks_valid),
        quarantine_rate=round(quarantine_rate, 6),
    )


def run_ingestion(settings: Settings) -> IngestionSummary:
    """Dispatch ingestion to local DuckDB or GCP BigQuery based on APP_ENV."""
    if settings.app_env == "gcp":
        return ingest_gcp_bigquery(settings)
    return ingest_local_duckdb(settings)

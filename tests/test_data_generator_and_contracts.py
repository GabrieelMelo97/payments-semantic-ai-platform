"""Tests for deterministic data generation, Pandera data contracts, quarantine, and idempotency."""

from __future__ import annotations

from pathlib import Path

import duckdb

from payments_platform.config import Settings
from payments_platform.data_generator import generate_payments_datasets, save_datasets_parquet
from payments_platform.ingestion import ingest_local_duckdb, validate_and_split_transactions


def test_data_generator_is_deterministic() -> None:
    ds1 = generate_payments_datasets(n_merchants=15, n_transactions=300, days=30, seed=42)
    ds2 = generate_payments_datasets(n_merchants=15, n_transactions=300, days=30, seed=42)

    assert ds1.merchants_current.equals(ds2.merchants_current)
    assert ds1.transactions.equals(ds2.transactions)
    assert ds1.chargebacks.equals(ds2.chargebacks)


def test_pandera_contract_quarantines_corrupt_transactions() -> None:
    ds = generate_payments_datasets(n_merchants=15, n_transactions=400, days=30, seed=42)
    valid_df, quarantine_df = validate_and_split_transactions(ds.transactions)

    assert len(quarantine_df) >= 4
    assert (valid_df["gross_amount_brl"] > 0).all()
    assert set(valid_df["status"]).issubset({"approved", "declined", "refunded"})
    assert "quarantine_reason" in quarantine_df.columns
    assert quarantine_df["quarantine_reason"].notna().all()


def test_local_ingestion_is_idempotent(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    settings = Settings(
        app_env="local",
        project_root=project_root,
        local_data_dir=tmp_path / "data",
        duckdb_path=tmp_path / "data" / "idempotent.duckdb",
    )
    ds = generate_payments_datasets(n_merchants=10, n_transactions=200, days=30, seed=7)
    save_datasets_parquet(ds, settings.resolved_data_dir)

    run1 = ingest_local_duckdb(settings)
    run2 = ingest_local_duckdb(settings)

    assert run1.transactions_valid == run2.transactions_valid
    assert run1.transactions_quarantined == run2.transactions_quarantined

    con = duckdb.connect(str(settings.resolved_duckdb_path), read_only=True)
    try:
        count = con.execute("select count(*) from raw.raw_transactions").fetchone()[0]
    finally:
        con.close()
    assert count == run1.transactions_valid

"""Shared pytest fixtures for Payments Semantic AI Platform."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from payments_platform.config import Settings
from payments_platform.data_generator import generate_payments_datasets, save_datasets_parquet
from payments_platform.ingestion import ingest_local_duckdb


@pytest.fixture(scope="session")
def e2e_settings(tmp_path_factory: pytest.TempPathFactory) -> Settings:
    """Build a complete, isolated local DuckDB + dbt warehouse once per test session."""
    work_dir = tmp_path_factory.mktemp("payments_e2e")
    data_dir = work_dir / "data"
    db_path = data_dir / "test_warehouse.duckdb"
    project_root = Path(__file__).resolve().parents[1]

    settings = Settings(
        app_env="local",
        project_root=project_root,
        local_data_dir=data_dir,
        duckdb_path=db_path,
        ai_provider="deterministic",
    )

    datasets = generate_payments_datasets(n_merchants=20, n_transactions=800, days=60, seed=42)
    save_datasets_parquet(datasets, data_dir)
    ingest_local_duckdb(settings)

    # Run dbt build against the isolated test DuckDB warehouse
    env = os.environ.copy()
    env["DUCKDB_PATH"] = str(db_path)
    dbt_bin = Path(sys.executable).parent / ("dbt.exe" if os.name == "nt" else "dbt")
    cmd = [
        str(dbt_bin),
        "build",
        "--project-dir",
        str(project_root / "dbt_project"),
        "--profiles-dir",
        str(project_root / "dbt_project"),
        "--target",
        "local",
    ]
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, f"dbt build failed:\n{proc.stdout}\n{proc.stderr}"

    return settings

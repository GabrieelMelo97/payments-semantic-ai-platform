"""Deterministic synthetic FinTech payments data generator.

Generates realistic merchant, transaction, and late-arriving chargeback datasets with
intentional production-grade data quality anomalies (duplicates, negative amounts,
invalid statuses, and historical MDR rate changes) to validate contracts, quarantine,
deduplication, and SCD Type 2 logic.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

MCC_CATEGORIES = [
    "ecommerce",
    "grocery",
    "restaurants",
    "travel",
    "saas_digital",
    "electronics",
]
REGIONS = ["Sudeste", "Sul", "Nordeste", "Centro-Oeste", "Norte"]
TIERS = ["SMB", "Mid-Market", "Enterprise"]
PAYMENT_METHODS = ["credit_card", "debit_card", "pix"]
CARD_BRANDS = ["visa", "mastercard", "elo"]
DECLINE_REASONS = [
    "insufficient_funds",
    "suspected_fraud",
    "issuer_unavailable",
    "invalid_cvv",
]
CHARGEBACK_REASONS = [
    "fraud_card_not_present",
    "merchandise_not_received",
    "duplicate_processing",
    "unrecognized_charge",
]

# Base MDR rates in basis points by tier (100 bps = 1%)
TIER_MDR_BPS = {"SMB": 310.0, "Mid-Market": 245.0, "Enterprise": 185.0}
TIER_INTERCHANGE_BPS = {"SMB": 155.0, "Mid-Market": 135.0, "Enterprise": 115.0}

# Intentional risk multipliers by MCC so analytics & AI copilot find real insights
MCC_CHARGEBACK_PROB = {
    "ecommerce": 0.014,
    "grocery": 0.002,
    "restaurants": 0.003,
    "travel": 0.022,
    "saas_digital": 0.008,
    "electronics": 0.028,
}


@dataclass(frozen=True)
class GeneratedDatasets:
    """Container for generated raw payments datasets."""

    merchants_initial: pd.DataFrame
    merchants_current: pd.DataFrame
    transactions: pd.DataFrame
    chargebacks: pd.DataFrame


def generate_payments_datasets(
    n_merchants: int = 60,
    n_transactions: int = 6000,
    days: int = 90,
    seed: int = 42,
    reference_end_date: datetime | None = None,
) -> GeneratedDatasets:
    """Generate deterministic FinTech acquiring datasets with realistic anomalies."""
    rng = np.random.default_rng(seed)
    end_dt = reference_end_date or datetime(2026, 11, 15, 23, 59, 0)
    start_dt = end_dt - timedelta(days=days)
    reprice_dt = start_dt + timedelta(days=days // 2)

    # 1. Merchants (initial state + mid-period MDR repricing for SCD Type 2)
    merchant_rows = []
    for idx in range(1, n_merchants + 1):
        tier = str(rng.choice(TIERS, p=[0.55, 0.30, 0.15]))
        mcc = str(rng.choice(MCC_CATEGORIES, p=[0.24, 0.18, 0.20, 0.12, 0.14, 0.12]))
        region = str(rng.choice(REGIONS, p=[0.42, 0.20, 0.18, 0.12, 0.08]))
        mdr_bps = round(TIER_MDR_BPS[tier] + float(rng.uniform(-20.0, 25.0)), 2)
        interchange_bps = round(
            min(mdr_bps - 40.0, TIER_INTERCHANGE_BPS[tier] + float(rng.uniform(-10.0, 15.0))),
            2,
        )
        merchant_rows.append(
            {
                "merchant_id": f"MRC-{idx:04d}",
                "merchant_name": f"{mcc.replace('_', ' ').title()} Store {idx:03d}",
                "mcc_category": mcc,
                "region": region,
                "tier": tier,
                "mdr_rate_bps": mdr_bps,
                "interchange_rate_bps": interchange_bps,
                "updated_at": start_dt,
            }
        )

    merchants_initial = pd.DataFrame(merchant_rows)

    # Simulate commercial MDR repricing for 30% of merchants mid-period (tests SCD2!)
    merchants_current = merchants_initial.copy()
    reprice_indices = rng.choice(n_merchants, size=max(1, int(n_merchants * 0.30)), replace=False)
    for m_idx in reprice_indices:
        delta_bps = float(rng.choice([-25.0, -15.0, 20.0, 35.0]))
        new_mdr = round(
            max(80.0, float(merchants_current.at[m_idx, "mdr_rate_bps"]) + delta_bps), 2
        )
        merchants_current.at[m_idx, "mdr_rate_bps"] = new_mdr
        merchants_current.at[m_idx, "updated_at"] = reprice_dt

    # 2. Transactions
    merchant_ids = merchants_initial["merchant_id"].to_numpy()
    merchant_mcc_map = dict(
        zip(merchants_initial["merchant_id"], merchants_initial["mcc_category"], strict=False)
    )

    tx_rows = []
    for tx_num in range(1, n_transactions + 1):
        m_id = str(rng.choice(merchant_ids))
        mcc = merchant_mcc_map[m_id]
        offset_seconds = int(rng.integers(0, days * 86400))
        created_at = start_dt + timedelta(seconds=offset_seconds)
        payment_method = str(rng.choice(PAYMENT_METHODS, p=[0.56, 0.22, 0.22]))

        if payment_method == "pix":
            card_brand = "pix_instant"
            installments = 1
            approval_prob = 0.965
        elif payment_method == "debit_card":
            card_brand = str(rng.choice(CARD_BRANDS, p=[0.45, 0.40, 0.15]))
            installments = 1
            approval_prob = 0.915
        else:
            card_brand = str(rng.choice(CARD_BRANDS, p=[0.44, 0.41, 0.15]))
            installments = int(
                rng.choice([1, 2, 3, 6, 10, 12], p=[0.45, 0.18, 0.15, 0.10, 0.07, 0.05])
            )
            approval_prob = 0.875 if mcc not in {"electronics", "travel"} else 0.835

        # Log-normal realistic ticket by MCC
        ticket_scale = {
            "grocery": 140.0,
            "restaurants": 95.0,
            "saas_digital": 220.0,
            "ecommerce": 310.0,
            "electronics": 980.0,
            "travel": 1350.0,
        }[mcc]
        gross_amount = round(float(rng.lognormal(mean=np.log(ticket_scale), sigma=0.55)), 2)
        gross_amount = max(12.50, min(gross_amount, 25000.0))

        roll = float(rng.random())
        if roll < approval_prob:
            status = "approved"
            decline_reason = None
        elif roll < approval_prob + 0.025:
            status = "refunded"
            decline_reason = None
        else:
            status = "declined"
            decline_reason = str(rng.choice(DECLINE_REASONS, p=[0.45, 0.25, 0.20, 0.10]))

        tx_rows.append(
            {
                "transaction_id": f"TX-{tx_num:07d}",
                "merchant_id": m_id,
                "created_at": created_at,
                "transaction_date": created_at.date(),
                "payment_method": payment_method,
                "card_brand": card_brand,
                "installments": installments,
                "gross_amount_brl": gross_amount,
                "status": status,
                "decline_reason": decline_reason,
            }
        )

    transactions_df = pd.DataFrame(tx_rows)

    # 3. Late-arriving chargebacks (only on approved credit/debit transactions)
    cb_rows = []
    cb_seq = 1
    approved_card_txs = transactions_df[
        (transactions_df["status"] == "approved") & (transactions_df["payment_method"] != "pix")
    ]
    for row in approved_card_txs.itertuples(index=False):
        mcc = merchant_mcc_map[row.merchant_id]
        cb_prob = MCC_CHARGEBACK_PROB[mcc]
        if float(rng.random()) < cb_prob:
            lag_days = int(rng.integers(3, 26))
            dispute_date = row.transaction_date + timedelta(days=lag_days)
            dispute_status = str(rng.choice(["lost", "won", "under_review"], p=[0.68, 0.22, 0.10]))
            cb_rows.append(
                {
                    "chargeback_id": f"CB-{cb_seq:06d}",
                    "transaction_id": row.transaction_id,
                    "dispute_date": dispute_date,
                    "reason_code": str(rng.choice(CHARGEBACK_REASONS, p=[0.52, 0.24, 0.09, 0.15])),
                    "disputed_amount_brl": float(row.gross_amount_brl),
                    "dispute_status": dispute_status,
                }
            )
            cb_seq += 1

    chargebacks_df = pd.DataFrame(cb_rows)

    # 4. Inject realistic dirty data into transactions:
    #    (a) 1.5% exact upstream duplicates (handled by dbt deduplication)
    n_dupes = max(5, int(len(transactions_df) * 0.015))
    dupes = transactions_df.sample(n=n_dupes, random_state=seed).copy()
    #    (b) ~0.5% corrupt rows (negative amount or invalid status) -> caught by Pandera Quarantine!
    n_corrupt = max(4, int(len(transactions_df) * 0.005))
    corrupt_rows = []
    for c_idx in range(n_corrupt):
        corrupt_rows.append(
            {
                "transaction_id": f"TX-CORRUPT-{c_idx + 1:04d}",
                "merchant_id": merchant_ids[c_idx % len(merchant_ids)],
                "created_at": end_dt - timedelta(days=1),
                "transaction_date": (end_dt - timedelta(days=1)).date(),
                "payment_method": "credit_card",
                "card_brand": "visa",
                "installments": 1,
                "gross_amount_brl": -150.0 if c_idx % 2 == 0 else 250.0,
                "status": "approved" if c_idx % 2 == 0 else "unknown_corrupt_status",
                "decline_reason": None,
            }
        )
    corrupt_df = pd.DataFrame(corrupt_rows)

    transactions_dirty = pd.concat([transactions_df, dupes, corrupt_df], ignore_index=True)

    logger.info(
        "Generated deterministic datasets: merchants=%d (repriced=%d), "
        "transactions=%d (dupes=%d, corrupt=%d), chargebacks=%d",
        len(merchants_current),
        len(reprice_indices),
        len(transactions_dirty),
        n_dupes,
        n_corrupt,
        len(chargebacks_df),
    )

    return GeneratedDatasets(
        merchants_initial=merchants_initial,
        merchants_current=merchants_current,
        transactions=transactions_dirty,
        chargebacks=chargebacks_df,
    )


def save_datasets_parquet(datasets: GeneratedDatasets, output_dir: Path) -> dict[str, Path]:
    """Persist generated datasets to local Parquet files."""
    raw_dir = output_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    paths = {
        "merchants_initial": raw_dir / "raw_merchants_initial.parquet",
        "merchants_current": raw_dir / "raw_merchants.parquet",
        "transactions": raw_dir / "raw_transactions.parquet",
        "chargebacks": raw_dir / "raw_chargebacks.parquet",
    }
    datasets.merchants_initial.to_parquet(paths["merchants_initial"], index=False)
    datasets.merchants_current.to_parquet(paths["merchants_current"], index=False)
    datasets.transactions.to_parquet(paths["transactions"], index=False)
    datasets.chargebacks.to_parquet(paths["chargebacks"], index=False)

    logger.info("Saved raw Parquet files to %s", raw_dir)
    return paths

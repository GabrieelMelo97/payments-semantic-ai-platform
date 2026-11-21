{{
    config(
        materialized='incremental',
        unique_key='transaction_id',
        on_schema_change='fail',
        incremental_strategy='merge' if target.type == 'bigquery' else 'delete+insert',
        partition_by={'field': 'transaction_date', 'data_type': 'date', 'granularity': 'day'} if target.type == 'bigquery' else none,
        cluster_by=['region', 'mcc_category', 'payment_method'] if target.type == 'bigquery' else none
    )
}}

with enriched as (
    select * from {{ ref('int_transactions_enriched') }}
    {% if is_incremental() %}
        where
            transaction_date >= (
                {% if target.type == 'bigquery' %}
                    select date_sub(max(transaction_date), interval 30 day)
                {% else %}
                    select max(transaction_date) - interval 30 day
                {% endif %}
                from {{ this }}
            )
    {% endif %}
)

select
    transaction_id,
    merchant_id,
    created_at,
    transaction_date,
    merchant_name,
    mcc_category,
    region,
    merchant_tier,
    payment_method,
    card_brand,
    installments,
    cast(gross_amount_brl as {{ dbt.type_float() }}) as gross_amount_brl,
    status,
    decline_reason,
    is_approved,
    cast(applied_mdr_rate_bps as {{ dbt.type_float() }}) as applied_mdr_rate_bps,
    cast(applied_interchange_rate_bps as {{ dbt.type_float() }}) as applied_interchange_rate_bps,
    chargeback_count,
    latest_dispute_date,
    cast(approved_tpv_brl as {{ dbt.type_float() }}) as approved_tpv_brl,
    cast(mdr_fee_brl as {{ dbt.type_float() }}) as mdr_fee_brl,
    cast(interchange_cost_brl as {{ dbt.type_float() }}) as interchange_cost_brl,
    cast(chargeback_loss_brl as {{ dbt.type_float() }}) as chargeback_loss_brl,
    cast(net_revenue_brl as {{ dbt.type_float() }}) as net_revenue_brl,
    cast(net_settlement_brl as {{ dbt.type_float() }}) as net_settlement_brl
from enriched

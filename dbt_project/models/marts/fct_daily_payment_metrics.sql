{{
    config(
        materialized='table',
        partition_by={'field': 'transaction_date', 'data_type': 'date', 'granularity': 'day'} if target.type == 'bigquery' else none,
        cluster_by=['region', 'mcc_category'] if target.type == 'bigquery' else none
    )
}}

select
    transaction_date,
    region,
    mcc_category,
    merchant_tier,
    payment_method,
    count(distinct transaction_id) as total_transactions,
    sum(case when is_approved then 1 else 0 end) as approved_transactions,
    round(sum(approved_tpv_brl), 2) as gross_tpv_brl,
    round(sum(mdr_fee_brl), 2) as mdr_revenue_brl,
    round(sum(interchange_cost_brl), 2) as interchange_cost_brl,
    round(sum(chargeback_loss_brl), 2) as chargeback_loss_brl,
    round(sum(net_revenue_brl), 2) as net_revenue_brl,
    round(sum(net_settlement_brl), 2) as net_settlement_brl
from {{ ref('fct_payments') }}
group by
    transaction_date,
    region,
    mcc_category,
    merchant_tier,
    payment_method

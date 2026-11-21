with transactions as (
    select * from {{ ref('stg_transactions') }}
),

merchants as (
    select * from {{ ref('stg_merchants') }}
),

mdr_history as (
    select * from {{ ref('stg_merchant_mdr_history') }}
),

chargebacks_agg as (
    select
        transaction_id,
        count(*) as chargeback_count,
        sum(
            case when dispute_status = 'lost' then disputed_amount_brl else 0.0 end
        ) as lost_chargeback_amount_brl,
        max(dispute_date) as latest_dispute_date
    from {{ ref('stg_chargebacks') }}
    group by transaction_id
),

joined as (
    select
        t.transaction_id,
        t.merchant_id,
        t.created_at,
        t.transaction_date,
        m.merchant_name,
        m.mcc_category,
        m.region,
        m.merchant_tier,
        t.payment_method,
        t.card_brand,
        t.installments,
        t.gross_amount_brl,
        t.status,
        t.decline_reason,
        (t.status = 'approved') as is_approved,
        case
            when t.payment_method = 'pix'
                then round(coalesce(h.mdr_rate_bps, m.current_mdr_rate_bps) * 0.35, 2)
            else coalesce(h.mdr_rate_bps, m.current_mdr_rate_bps)
        end as applied_mdr_rate_bps,
        case
            when t.payment_method = 'pix' then 0.0
            else coalesce(h.interchange_rate_bps, m.current_interchange_rate_bps)
        end as applied_interchange_rate_bps,
        coalesce(cb.chargeback_count, 0) as chargeback_count,
        coalesce(cb.lost_chargeback_amount_brl, 0.0) as raw_chargeback_loss_brl,
        cb.latest_dispute_date
    from transactions as t
    inner join merchants as m
        on t.merchant_id = m.merchant_id
    left join mdr_history as h
        on
            t.merchant_id = h.merchant_id
            and t.created_at >= h.valid_from
            and t.created_at < h.valid_to
    left join chargebacks_agg as cb
        on t.transaction_id = cb.transaction_id
),

financials as (
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
        gross_amount_brl,
        status,
        decline_reason,
        is_approved,
        applied_mdr_rate_bps,
        applied_interchange_rate_bps,
        chargeback_count,
        latest_dispute_date,
        case
            when is_approved then round(gross_amount_brl, 4)
            else 0.0
        end as approved_tpv_brl,
        case
            when is_approved then round(gross_amount_brl * (applied_mdr_rate_bps / 10000.0), 4)
            else 0.0
        end as mdr_fee_brl,
        case
            when is_approved
                then round(gross_amount_brl * (applied_interchange_rate_bps / 10000.0), 4)
            else 0.0
        end as interchange_cost_brl,
        case
            when is_approved then round(raw_chargeback_loss_brl, 4)
            else 0.0
        end as chargeback_loss_brl
    from joined
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
    gross_amount_brl,
    status,
    decline_reason,
    is_approved,
    applied_mdr_rate_bps,
    applied_interchange_rate_bps,
    chargeback_count,
    latest_dispute_date,
    approved_tpv_brl,
    mdr_fee_brl,
    interchange_cost_brl,
    chargeback_loss_brl,
    round(mdr_fee_brl - interchange_cost_brl - chargeback_loss_brl, 4) as net_revenue_brl,
    round(approved_tpv_brl - mdr_fee_brl - chargeback_loss_brl, 4) as net_settlement_brl
from financials

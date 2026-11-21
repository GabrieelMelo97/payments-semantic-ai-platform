-- Singular Test: Financial Accounting Reconciliation
-- Verifies that for every approved transaction,
-- Approved TPV - MDR Fee - Chargeback Loss == Net Merchant Settlement (within R$ 0.01 rounding).

select
    transaction_id,
    approved_tpv_brl,
    mdr_fee_brl,
    chargeback_loss_brl,
    net_settlement_brl,
    abs((approved_tpv_brl - mdr_fee_brl - chargeback_loss_brl) - net_settlement_brl) as diff_brl
from {{ ref('fct_payments') }}
where abs((approved_tpv_brl - mdr_fee_brl - chargeback_loss_brl) - net_settlement_brl) > 0.01

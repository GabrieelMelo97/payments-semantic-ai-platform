-- Singular Test: Idempotency & Deduplication Guarantee
-- Ensures fct_payments contains strictly 1 row per transaction_id even with upstream duplicates.

select
    transaction_id,
    count(*) as occurrences
from {{ ref('fct_payments') }}
group by transaction_id
having count(*) > 1

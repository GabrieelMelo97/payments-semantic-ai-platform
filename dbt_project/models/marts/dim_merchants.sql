with merchants as (
    select * from {{ ref('stg_merchants') }}
),

mdr_versions as (
    select
        merchant_id,
        count(*) as historical_rate_versions,
        min(mdr_rate_bps) as min_historical_mdr_bps,
        max(mdr_rate_bps) as max_historical_mdr_bps
    from {{ ref('stg_merchant_mdr_history') }}
    group by merchant_id
)

select
    m.merchant_id,
    m.merchant_name,
    m.mcc_category,
    m.region,
    m.merchant_tier,
    m.current_mdr_rate_bps,
    m.current_interchange_rate_bps,
    coalesce(v.historical_rate_versions, 1) as historical_rate_versions,
    coalesce(v.min_historical_mdr_bps, m.current_mdr_rate_bps) as min_historical_mdr_bps,
    coalesce(v.max_historical_mdr_bps, m.current_mdr_rate_bps) as max_historical_mdr_bps,
    m.updated_at
from merchants as m
left join mdr_versions as v
    on m.merchant_id = v.merchant_id

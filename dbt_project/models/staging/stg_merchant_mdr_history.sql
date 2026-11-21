with deduped_versions as (
    select
        cast(merchant_id as {{ dbt.type_string() }}) as merchant_id,
        cast(mdr_rate_bps as {{ dbt.type_float() }}) as mdr_rate_bps,
        cast(interchange_rate_bps as {{ dbt.type_float() }}) as interchange_rate_bps,
        cast(updated_at as {{ dbt.type_timestamp() }}) as valid_from,
        row_number() over (
            partition by merchant_id, updated_at
            order by updated_at desc
        ) as version_rn
    from {{ source('payments_raw', 'raw_merchants_history') }}
),

scd2_intervals as (
    select
        merchant_id,
        mdr_rate_bps,
        interchange_rate_bps,
        valid_from,
        lead(valid_from) over (
            partition by merchant_id
            order by valid_from asc
        ) as valid_to
    from deduped_versions
    where version_rn = 1
)

select
    merchant_id,
    mdr_rate_bps,
    interchange_rate_bps,
    valid_from,
    coalesce(valid_to, cast('2099-12-31 23:59:59' as {{ dbt.type_timestamp() }})) as valid_to
from scd2_intervals

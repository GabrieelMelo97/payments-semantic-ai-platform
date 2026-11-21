with source_merchants as (
    select
        cast(merchant_id as {{ dbt.type_string() }}) as merchant_id,
        cast(merchant_name as {{ dbt.type_string() }}) as merchant_name,
        lower(cast(mcc_category as {{ dbt.type_string() }})) as mcc_category,
        cast(region as {{ dbt.type_string() }}) as region,
        cast(tier as {{ dbt.type_string() }}) as merchant_tier,
        cast(mdr_rate_bps as {{ dbt.type_float() }}) as current_mdr_rate_bps,
        cast(interchange_rate_bps as {{ dbt.type_float() }}) as current_interchange_rate_bps,
        cast(updated_at as {{ dbt.type_timestamp() }}) as updated_at
    from {{ source('payments_raw', 'raw_merchants') }}
)

select *
from source_merchants

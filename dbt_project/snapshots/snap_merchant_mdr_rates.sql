{% snapshot snap_merchant_mdr_rates %}

{{
    config(
        unique_key='merchant_id',
        strategy='timestamp',
        updated_at='updated_at',
        invalidate_hard_deletes=true
    )
}}

select
    merchant_id,
    merchant_name,
    mcc_category,
    region,
    tier,
    mdr_rate_bps,
    interchange_rate_bps,
    updated_at
from {{ source('payments_raw', 'raw_merchants') }}

{% endsnapshot %}

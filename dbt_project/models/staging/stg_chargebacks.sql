select
    cast(chargeback_id as {{ dbt.type_string() }}) as chargeback_id,
    cast(transaction_id as {{ dbt.type_string() }}) as transaction_id,
    cast(dispute_date as date) as dispute_date,
    lower(cast(reason_code as {{ dbt.type_string() }})) as reason_code,
    cast(disputed_amount_brl as {{ dbt.type_float() }}) as disputed_amount_brl,
    lower(cast(dispute_status as {{ dbt.type_string() }})) as dispute_status
from {{ source('payments_raw', 'raw_chargebacks') }}

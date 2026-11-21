with ranked_transactions as (
    select
        cast(transaction_id as {{ dbt.type_string() }}) as transaction_id,
        cast(merchant_id as {{ dbt.type_string() }}) as merchant_id,
        cast(created_at as {{ dbt.type_timestamp() }}) as created_at,
        cast(transaction_date as date) as transaction_date,
        lower(cast(payment_method as {{ dbt.type_string() }})) as payment_method,
        lower(cast(card_brand as {{ dbt.type_string() }})) as card_brand,
        cast(installments as {{ dbt.type_int() }}) as installments,
        cast(gross_amount_brl as {{ dbt.type_float() }}) as gross_amount_brl,
        lower(cast(status as {{ dbt.type_string() }})) as status,
        cast(decline_reason as {{ dbt.type_string() }}) as decline_reason,
        row_number() over (
            partition by transaction_id
            order by created_at desc
        ) as dedup_rn
    from {{ source('payments_raw', 'raw_transactions') }}
)

select
    transaction_id,
    merchant_id,
    created_at,
    transaction_date,
    payment_method,
    card_brand,
    installments,
    gross_amount_brl,
    status,
    decline_reason
from ranked_transactions
where dedup_rn = 1

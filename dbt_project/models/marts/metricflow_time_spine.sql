{{ config(materialized='table') }}

{% if target.type == 'bigquery' %}
    select date_day
    from unnest(generate_date_array(date('2025-01-01'), date('2027-12-31'))) as date_day
{% else %}
    select cast(range as date) as date_day
    from range(date '2025-01-01', date '2028-01-01', interval 1 day)
{% endif %}

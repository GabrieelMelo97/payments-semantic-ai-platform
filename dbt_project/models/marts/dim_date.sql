with spine as (
    select date_day
    from {{ ref('metricflow_time_spine') }}
)

select
    date_day,
    extract(year from date_day) as calendar_year,
    extract(month from date_day) as calendar_month,
    extract(day from date_day) as day_of_month,
    extract(dayofweek from date_day) as day_of_week
from spine

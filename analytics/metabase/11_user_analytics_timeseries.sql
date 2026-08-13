-- USER ANALYTICS - all four metrics as one line chart.
--
-- Returns long format (bucket_start, metric, value), which is what Metabase's
-- multi-series line chart wants:
--   Visualization : Line
--   X axis        : bucket_start
--   Y axis        : value
--   Series        : metric
--
-- Uses the same {{range}} variable as the scorecards, so one dashboard filter
-- drives the whole tab. See 10_user_analytics_scorecards.sql for the variable
-- setup.
--
-- The bucket is derived from the range rather than being a second dropdown:
-- hourly up to 3 days, daily beyond that. A 90-day range in hourly buckets is
-- 2,160 points of noise. To make it an explicit control instead, replace the
-- `bucket` expression in `params` with a {{bucket}} variable ('hour'/'day'/'week').
--
-- Buckets are zero-filled via generate_series so the lines don't break across
-- quiet periods - without it, a metric with no rows in an hour simply has no
-- point there and Metabase draws a straight line over the gap.

with params as (
    select
        cast({{range}} as interval) as window_len,
        case
            when cast({{range}} as interval) <= interval '3 days' then 'hour'
            else 'day'
        end as bucket
),

bounds as (
    select
        p.bucket,
        date_trunc(p.bucket, now() - p.window_len) as start_at,
        now() as end_at
    from params p
),

buckets as (
    select generate_series(
        b.start_at,
        b.end_at,
        ('1 ' || b.bucket)::interval
    ) as bucket_start
    from bounds b
),

new_users as (
    select
        date_trunc(b.bucket, u.created_at) as bucket_start,
        count(*) as value
    from app_users_appuser u
    cross join bounds b
    where u.created_at >= b.start_at
      and u.is_anonymous = false
      and u.is_disabled = false
    group by 1
),

new_paid_users as (
    select
        date_trunc(b.bucket, fp.first_paid_at) as bucket_start,
        count(*) as value
    from (
        select t.workspace_id, min(t.created_at) as first_paid_at
        from app_users_appusertransaction t
        where t.charged_amount > 0
        group by t.workspace_id
    ) fp
    cross join bounds b
    where fp.first_paid_at >= b.start_at
    group by 1
),

ask_gooey_queries as (
    select
        date_trunc(b.bucket, sr.created_at) as bucket_start,
        count(*) as value
    from bots_savedrun sr
    cross join bounds b
    where sr.created_at >= b.start_at
      and sr.surface = 3
    group by 1
),

new_deployments as (
    select
        date_trunc(b.bucket, bi.created_at) as bucket_start,
        count(*) as value
    from bots_botintegration bi
    cross join bounds b
    where bi.created_at >= b.start_at
    group by 1
),

metrics as (
    select 'New users'         as metric, bucket_start, value from new_users
    union all
    select 'New paid users',    bucket_start, value from new_paid_users
    union all
    select 'Ask Gooey queries', bucket_start, value from ask_gooey_queries
    union all
    select 'New deployments',   bucket_start, value from new_deployments
),

grid as (
    select bk.bucket_start, m.metric
    from buckets bk
    cross join (values
        ('New users'),
        ('New paid users'),
        ('Ask Gooey queries'),
        ('New deployments')
    ) m(metric)
)

select
    g.bucket_start,
    g.metric,
    coalesce(mt.value, 0) as value
from grid g
left join metrics mt
    on mt.bucket_start = g.bucket_start
   and mt.metric = g.metric
order by g.bucket_start, g.metric

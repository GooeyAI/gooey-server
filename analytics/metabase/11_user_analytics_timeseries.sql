-- USER ANALYTICS - all four metrics over time, wide format.
--
-- Returns one row per time bucket with one column per metric:
--
--     bucket_start | new_users | new_paid_users | ask_gooey_queries | new_deployments
--
-- Wide format (rather than long) is what makes a COMBO chart possible: each
-- column is its own series, so you can set bars vs line and left vs right axis
-- per metric. A long-format result forces every series to share one display
-- type and one axis.
--
--   Visualization : Combo   (or Line/Bar if you want them all the same)
--   X axis        : bucket_start
--   Y axis        : select all four count columns
--   Then per series, under Settings -> Series:
--     ask_gooey_queries -> Line, RIGHT axis
--     everything else   -> Bar,  LEFT axis
--
-- The right axis matters: Ask Gooey queries run one to two orders of magnitude
-- above new paid users, so on a shared axis the small series flatten to zero.
--
-- Bucket size is derived from the range - hourly up to 3 days, daily beyond -
-- because 90 days of hourly buckets is 2,160 points of noise. To make it an
-- explicit control, replace the `bucket` expression with a {{bucket}} variable
-- offering 'hour' / 'day' / 'week'.
--
-- Buckets are zero-filled with generate_series so quiet periods read as zero
-- rather than having the line drawn straight over the gap.

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
    select date_trunc(b.bucket, u.created_at) as bucket_start, count(*) as value
    from app_users_appuser u
    cross join bounds b
    where u.created_at >= b.start_at
      and u.is_anonymous = false
      and u.is_disabled = false
    group by 1
),

new_paid_users as (
    select date_trunc(b.bucket, fp.first_paid_at) as bucket_start, count(*) as value
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
    select date_trunc(b.bucket, sr.created_at) as bucket_start, count(*) as value
    from bots_savedrun sr
    cross join bounds b
    where sr.created_at >= b.start_at
      and sr.surface = 3
    group by 1
),

new_deployments as (
    select date_trunc(b.bucket, bi.created_at) as bucket_start, count(*) as value
    from bots_botintegration bi
    cross join bounds b
    where bi.created_at >= b.start_at
    group by 1
)

select
    bk.bucket_start,
    coalesce(nu.value, 0) as new_users,
    coalesce(np.value, 0) as new_paid_users,
    coalesce(ag.value, 0) as ask_gooey_queries,
    coalesce(nd.value, 0) as new_deployments
from buckets bk
left join new_users         nu on nu.bucket_start = bk.bucket_start
left join new_paid_users    np on np.bucket_start = bk.bucket_start
left join ask_gooey_queries ag on ag.bucket_start = bk.bucket_start
left join new_deployments   nd on nd.bucket_start = bk.bucket_start
order by bk.bucket_start

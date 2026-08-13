-- USER ANALYTICS - the four headline cards, as Trend (Smart Scalar) cards.
--
-- Each query returns TWO rows: the previous period and the current one, e.g.
--
--     period_start              | new_users
--     2026-07-30 12:00:00+00    | 812        <- previous 7 days
--     2026-08-06 12:00:00+00    | 907        <- current 7 days
--
-- That shape is what Metabase's Trend visualization needs to render the big
-- number with "↑ 11.7% vs. previous period" underneath. A single-row scalar
-- query cannot show a comparison - there is nothing to compare against.
--
--   Visualization : Trend
--   X / dimension : period_start
--   Y / metric    : the count column
--
-- The comparison window always equals the selected range: pick "7 days" and it
-- compares against the 7 days before that; pick "24 hours" and it compares
-- against the previous 24 hours.
--
-- Want a plain number with no comparison instead? Delete the first branch of
-- the `periods` UNION and switch the visualization to Number.
--
-- This file holds FOUR separate queries - one per card. See SETUP_GUIDE.md for
-- the {{range}} variable setup.


-- ===========================================================================
-- 1. New users
-- Registered signups only; anonymous sessions and banned accounts excluded.
-- ===========================================================================
with params as (
    select cast({{range}} as interval) as window_len
),
periods as (
    select now() - p.window_len * 2 as period_start,
           now() - p.window_len * 2 as from_at,
           now() - p.window_len     as to_at
    from params p
    union all
    select now() - p.window_len, now() - p.window_len, now()
    from params p
)
select
    pr.period_start,
    (
        select count(*)
        from app_users_appuser u
        where u.created_at >= pr.from_at
          and u.created_at <  pr.to_at
          and u.is_anonymous = false
          and u.is_disabled = false
    ) as new_users
from periods pr
order by pr.period_start;


-- ===========================================================================
-- 2. New paid users
-- Billing entities whose FIRST-EVER charged transaction lands in the period,
-- so existing subscribers renewing are not counted. Keyed on workspace because
-- that is the billing entity - swap to t.user_id for per-individual.
-- ===========================================================================
with params as (
    select cast({{range}} as interval) as window_len
),
periods as (
    select now() - p.window_len * 2 as period_start,
           now() - p.window_len * 2 as from_at,
           now() - p.window_len     as to_at
    from params p
    union all
    select now() - p.window_len, now() - p.window_len, now()
    from params p
),
first_payment as (
    select t.workspace_id, min(t.created_at) as first_paid_at
    from app_users_appusertransaction t
    where t.charged_amount > 0
    group by t.workspace_id
)
select
    pr.period_start,
    (
        select count(*)
        from first_payment fp
        where fp.first_paid_at >= pr.from_at
          and fp.first_paid_at <  pr.to_at
    ) as new_paid_users
from periods pr
order by pr.period_start;


-- ===========================================================================
-- 3. Ask Gooey queries
-- Prompts submitted to the Gooey Builder (SavedRun.Surface.builder_prompt = 3,
-- shown as "Ask Prompt" in the admin). Counts prompts, not conversations.
-- ===========================================================================
with params as (
    select cast({{range}} as interval) as window_len
),
periods as (
    select now() - p.window_len * 2 as period_start,
           now() - p.window_len * 2 as from_at,
           now() - p.window_len     as to_at
    from params p
    union all
    select now() - p.window_len, now() - p.window_len, now()
    from params p
)
select
    pr.period_start,
    (
        select count(*)
        from bots_savedrun sr
        where sr.created_at >= pr.from_at
          and sr.created_at <  pr.to_at
          and sr.surface = 3
    ) as ask_gooey_queries
from periods pr
order by pr.period_start;


-- ===========================================================================
-- 4. New deployments
-- One row per BotIntegration created - a bot connected to a channel
-- (WhatsApp / Slack / Web / Telegram / ...).
-- ===========================================================================
with params as (
    select cast({{range}} as interval) as window_len
),
periods as (
    select now() - p.window_len * 2 as period_start,
           now() - p.window_len * 2 as from_at,
           now() - p.window_len     as to_at
    from params p
    union all
    select now() - p.window_len, now() - p.window_len, now()
    from params p
)
select
    pr.period_start,
    (
        select count(*)
        from bots_botintegration bi
        where bi.created_at >= pr.from_at
          and bi.created_at <  pr.to_at
    ) as new_deployments
from periods pr
order by pr.period_start;

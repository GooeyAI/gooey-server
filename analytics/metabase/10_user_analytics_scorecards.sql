-- USER ANALYTICS - the four scorecards.
--
-- This file holds FOUR separate queries. Metabase's "Number" visualization shows
-- only the first cell of a result, so each one goes in its own question/card.
-- Paste one query per question and set the visualization to Number.
--
-- Every query uses the same {{range}} variable, so a single dashboard filter
-- drives all four. Set it up as:
--   Variable type : Text
--   Widget label  : Time range
--   Widget type   : Search box -> change to "Dropdown"
--   How to filter : "Custom list" with one value per line:
--       24 hours
--       3 days
--       7 days
--       14 days
--       30 days
--       90 days
--   Default       : 7 days     <- required, or the card errors when unfiltered
--
-- The strings are fed straight to Postgres as an interval, which is why they
-- read "3 days" rather than "Past 3 days". If you want prettier labels, see the
-- README section "Time range dropdown".


-- ===========================================================================
-- 1. New users
-- Registered signups only - anonymous sessions are counted separately below
-- and are not what anyone means by "new users".
-- ===========================================================================
select count(*) as new_users
from app_users_appuser u
where u.created_at >= now() - cast({{range}} as interval)
  and u.is_anonymous = false
  and u.is_disabled = false;


-- ===========================================================================
-- 2. New paid users
-- Billing entities whose FIRST-EVER charged transaction lands in the window -
-- not "everyone who paid", which would count existing subscribers renewing.
--
-- Keyed on workspace because that is the billing entity: a team with 5 members
-- that starts paying is one new paid customer, not five. Swap workspace_id for
-- user_id below if you want it keyed on the individual instead.
-- ===========================================================================
with first_payment as (
    select
        t.workspace_id,
        min(t.created_at) as first_paid_at
    from app_users_appusertransaction t
    where t.charged_amount > 0
    group by t.workspace_id
)
select count(*) as new_paid_users
from first_payment
where first_paid_at >= now() - cast({{range}} as interval);


-- ===========================================================================
-- 3. Ask Gooey queries
-- Prompts submitted to the Gooey Builder (SavedRun.Surface.builder_prompt = 3,
-- labelled "Ask Prompt" in the admin).
-- ===========================================================================
select count(*) as ask_gooey_queries
from bots_savedrun sr
where sr.created_at >= now() - cast({{range}} as interval)
  and sr.surface = 3;


-- ===========================================================================
-- 4. New deployments
-- A deployment is a BotIntegration - one row per bot connected to a channel
-- (WhatsApp / Slack / Web / Telegram / ...).
-- ===========================================================================
select count(*) as new_deployments
from bots_botintegration bi
where bi.created_at >= now() - cast({{range}} as interval);

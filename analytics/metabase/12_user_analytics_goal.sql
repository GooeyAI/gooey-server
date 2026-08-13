-- USER ANALYTICS - progress toward a goal (the green bar card).
--
--   Visualization : Progress
--   Goal          : set in the visualization settings, NOT in SQL
--
-- Metabase's Progress card takes a single number and compares it to a goal you
-- type into the viz settings. The goal is a dashboard setting, so changing the
-- target later needs no SQL edit.
--
-- Note this one deliberately ignores {{range}} and uses month-to-date: a
-- progress bar only means something against a fixed target period. Mixing it
-- with an arbitrary rolling window would let someone pick "24 hours" and see
-- 3% of a monthly goal, which reads as failure rather than as "it's the 1st".
--
-- If you'd rather it follow the dropdown, swap the where clause for
--   created_at >= now() - cast({{range}} as interval)
-- and remember the goal then means "per selected range".

-- ===========================================================================
-- New paid users, month to date
-- ===========================================================================
with first_payment as (
    select t.workspace_id, min(t.created_at) as first_paid_at
    from app_users_appusertransaction t
    where t.charged_amount > 0
    group by t.workspace_id
)
select count(*) as new_paid_users_mtd
from first_payment
where first_paid_at >= date_trunc('month', now());


-- ===========================================================================
-- Variant: new users, month to date
-- ===========================================================================
select count(*) as new_users_mtd
from app_users_appuser u
where u.created_at >= date_trunc('month', now())
  and u.is_anonymous = false
  and u.is_disabled = false;

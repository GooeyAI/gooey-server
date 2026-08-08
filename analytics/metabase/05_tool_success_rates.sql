-- Per-tool call volume and success rate.
--
-- `no_result` is a call the transcript has no answer for - the run died before
-- the tool returned. It is excluded from the success rate on purpose: that's a
-- broken run, not a broken tool.
--
-- Replace {{#02-builder-tool-calls}} with the real card reference.

with calls as (
    select * from {{#02-builder-tool-calls}}
)

select
    tool_name                                     as tool,
    count(*)                                      as calls,
    count(*) filter (where ok)                    as succeeded,
    count(*) filter (where ok is false)           as failed,
    count(*) filter (where ok is null)            as no_result,
    round(
        100.0 * count(*) filter (where ok)
        / nullif(count(*) filter (where ok is not null), 0),
        1
    )                                             as success_pct,
    count(distinct saved_run_id)                  as prompts,
    count(distinct uid)                           as users
from calls
where tool_name is not null
group by tool_name
order by calls desc

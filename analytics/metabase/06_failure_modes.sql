-- Top failure modes, counting run-level errors and tool-level errors together.
--
-- Run-level errors are counted once per prompt; tool-level errors once per
-- failed call, grouped by the tool that produced them.
--
-- Replace {{#02-builder-tool-calls}} with the real card reference.

with calls as (
    select * from {{#02-builder-tool-calls}}
),

run_errors as (
    select
        'run'                                     as source,
        coalesce(nullif(min(error_type), ''), 'Unknown') as error,
        saved_run_id
    from calls
    where error_msg <> '' or error_type <> ''
    group by saved_run_id
),

tool_errors as (
    select
        'tool: ' || tool_name                     as source,
        coalesce(nullif(left(error, 120), ''), 'Unknown') as error,
        saved_run_id
    from calls
    where ok is false
)

select
    source,
    error,
    count(*)                     as occurrences,
    count(distinct saved_run_id) as prompts_affected
from (
    select source, error, saved_run_id from run_errors
    union all
    select source, error, saved_run_id from tool_errors
) all_errors
group by source, error
order by occurrences desc
limit 50

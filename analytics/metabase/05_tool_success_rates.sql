-- Per-tool call volume and success rate.
--
-- `no_result` is a call the transcript has no answer for - the run died before
-- the tool returned. It is excluded from the success rate on purpose: that's a
-- broken run, not a broken tool.
--

with builder_runs as (
    select
        sr.id,
        sr.run_id,
        sr.uid,
        sr.workspace_id,
        sr.message_thread_id,
        sr.created_at,
        sr.run_time,
        sr.price,
        sr.run_status,
        sr.error_msg,
        sr.error_type,
        sr.state ->> 'input_prompt' as input_prompt,
        -- final_prompt is typed `list | str` in the ResponseModel, so anything
        -- that isn't an array becomes an empty one rather than an error
        case
            when jsonb_typeof(sr.state -> 'final_prompt') = 'array'
                then sr.state -> 'final_prompt'
            else '[]'::jsonb
        end as final_prompt
    from bots_savedrun sr
    where sr.surface = 3  -- SavedRun.Surface.builder_prompt
        [[and {{created_at}}]]
),

messages as (
    select
        b.id as saved_run_id,
        msg.value as msg,
        msg.ordinality as pos
    from builder_runs b
    cross join lateral jsonb_array_elements(b.final_prompt)
        with ordinality as msg(value, ordinality)
),

tool_calls as (
    select
        m.saved_run_id,
        m.pos,
        tc.value ->> 'id' as tool_call_id,
        tc.value -> 'function' ->> 'name' as tool_name,
        tc.value -> 'function' ->> 'arguments' as arguments
    from messages m
    -- the guard lives inside the lateral, not in a WHERE: a set-returning
    -- function is evaluated before the filter, so a non-array `tool_calls`
    -- would abort the whole query
    cross join lateral jsonb_array_elements(
        case
            when m.msg ->> 'role' = 'assistant'
                and jsonb_typeof(m.msg -> 'tool_calls') = 'array'
                then m.msg -> 'tool_calls'
            else '[]'::jsonb
        end
    ) as tc
),

tool_results as (
    select
        m.saved_run_id,
        m.msg ->> 'tool_call_id' as tool_call_id,
        -- tool content is always json.dumps(...) output in practice
        -- (functions/base_llm_tool.py:call_json), but only cast what actually
        -- looks like JSON so one odd row can't take the query down
        case
            when m.msg ->> 'content' ~ '^\s*[\{\[]'
                then (m.msg ->> 'content')::jsonb
        end as result
    from messages m
    where m.msg ->> 'role' = 'tool'
),

calls as (
select
    b.id as saved_run_id,
    b.run_id,
    b.uid,
    b.workspace_id,
    b.message_thread_id,
    b.created_at,
    b.input_prompt,
    b.error_msg,
    b.error_type,
    b.run_status,
    b.run_time,
    b.price,
    c.tool_call_id,
    c.tool_name,
    c.arguments,
    -- null = the run died before the tool returned. Deliberately NOT false:
    -- that's a run that broke, not a tool that failed, and conflating the two
    -- skews the success rates.
    case
        when r.result is null then null
        when coalesce(r.result ->> 'error', '') <> '' then false
        when r.result ->> 'success' = 'false' then false
        else true
    end as ok,
    -- the three failure shapes the builder tools actually return: a bare error
    -- string (save tools), a structured error object (run_workflow), and
    -- success=false (deploy tool)
    case
        when jsonb_typeof(r.result -> 'error') = 'object'
            then coalesce(r.result -> 'error' ->> 'msg', r.result -> 'error' ->> 'type')
        else r.result ->> 'error'
    end as error,
    coalesce(
        r.result ->> 'run_url',
        r.result ->> 'deployment_url',
        r.result ->> 'workflow_url'
    ) as result_url
from builder_runs b
left join tool_calls c on c.saved_run_id = b.id
left join tool_results r
    on r.saved_run_id = c.saved_run_id
    and r.tool_call_id = c.tool_call_id
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

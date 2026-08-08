-- One row per Gooey Builder prompt: what the user asked, and what they got.
--
-- generates once the model from 02 is saved (it looks like {{#123-builder-tool-calls}}).
--
-- The outcome mirrors daras_ai_v2.builder_analytics.classify_outcome: it reports
-- the furthest step a prompt reached, so a successful save followed by a failed
-- deploy reads as "Saved workflow", not "Tool error".

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
),

per_prompt as (
    select
        saved_run_id,
        min(run_id)                       as run_id,
        min(uid)                          as uid,
        min(workspace_id)                 as workspace_id,
        min(message_thread_id)            as message_thread_id,
        min(created_at)                   as created_at,
        min(input_prompt)                 as input_prompt,
        min(error_msg)                    as error_msg,
        min(error_type)                   as error_type,
        min(run_status)                   as run_status,
        min(run_time)                     as run_time,
        min(price)                        as price,
        count(tool_name)                  as tool_calls,
        count(*) filter (where ok is false)                                  as failed_calls,
        bool_or(ok and tool_name = 'deploy_workflow')                        as deployed,
        bool_or(ok and tool_name in ('save_workflow', 'save_as_new_workflow')) as saved,
        bool_or(ok and tool_name = 'run_workflow')                           as ran,
        bool_or(ok and tool_name = 'update_workflow_state')                  as edited,
        bool_or(ok and tool_name in ('search_workflows', 'fetch_workflow_state')) as searched,
        string_agg(
            case when ok is null then '…' when ok then '✅' else '❌' end || ' ' || tool_name,
            '  ' order by tool_call_id
        ) filter (where tool_name is not null)                               as tools,
        -- save/deploy attribution comes from the url the tool handed back, so
        -- it's exact rather than a time-window guess
        max(result_url) filter (where ok and result_url is not null)         as result_url
    from calls
    group by saved_run_id
)

select
    p.created_at,
    case
        when p.error_msg <> ''                   then '❌ Run failed'
        when p.run_status <> ''                  then '⏳ Running'
        when coalesce(p.deployed, false)         then '🚀 Deployed'
        when coalesce(p.saved, false)            then '💾 Saved workflow'
        when coalesce(p.ran, false)              then '▶️ Ran workflow'
        when coalesce(p.edited, false)           then '✏️ Edited workflow'
        when coalesce(p.searched, false)         then '🔍 Searched'
        when p.tool_calls > 0                    then '⚠️ Tool error'
        else '💬 Answered'
    end                                          as outcome,
    coalesce(nullif(u.display_name, ''), u.email, u.phone_number, p.uid) as "user",
    coalesce(nullif(w.name, ''), 'Personal')     as workspace,
    left(p.input_prompt, 300)                    as prompt,
    t.title                                      as conversation,
    p.tools,
    p.tool_calls,
    p.failed_calls,
    p.run_time,
    p.price                                      as credits,
    nullif(p.error_type, '')                     as error_type,
    'https://gooey.ai/agent/?run_id=' || p.run_id || '&uid=' || p.uid as builder_run_url,
    coalesce(
        p.result_url,
        -- fall back to the child run the builder spawned, when there is one
        'https://gooey.ai/agent/?run_id=' || child.run_id || '&uid=' || child.uid
    )                                            as workflow_url
from per_prompt p
left join app_users_appuser u on u.uid = p.uid
left join workspaces_workspace w on w.id = p.workspace_id
left join bots_messagethread t on t.id = p.message_thread_id
left join lateral (
    select c.run_id, c.uid
    from bots_savedrun c
    where c.parent_builder_saved_run_id = p.saved_run_id
    order by c.created_at desc
    limit 1
) child on true
order by p.created_at desc

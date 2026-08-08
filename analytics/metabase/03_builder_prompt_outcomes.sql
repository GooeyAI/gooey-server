-- One row per Gooey Builder prompt: what the user asked, and what they got.
--
-- Replace {{#02-builder-tool-calls}} with the real card reference Metabase
-- generates once the model from 02 is saved (it looks like {{#123-builder-tool-calls}}).
--
-- The outcome mirrors daras_ai_v2.builder_analytics.classify_outcome: it reports
-- the furthest step a prompt reached, so a successful save followed by a failed
-- deploy reads as "Saved workflow", not "Tool error".

with calls as (
    select * from {{#02-builder-tool-calls}}
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

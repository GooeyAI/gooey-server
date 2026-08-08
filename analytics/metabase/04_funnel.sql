-- Builder funnel: prompt -> tool attempted -> workflow touched -> saved -> deployed.
--
-- Visualization: Funnel (Step = step, Measure = prompts). The `step_no` column
-- is there only to keep the steps in order - hide it in the chart settings.
--
-- Replace {{#02-builder-tool-calls}} with the real card reference.

with calls as (
    select * from {{#02-builder-tool-calls}}
),

-- Each step counts prompts that got *at least* this far, so the funnel is
-- monotonic: saving a workflow implies touching one, deploying implies saving.
-- Without this, a prompt that saved without a separate edit/run step would make
-- "Saved" wider than "Workflow touched" and the funnel would render inverted.
per_prompt as (
    select
        c.saved_run_id,
        count(c.tool_name) > 0 as attempted_tool,
        bool_or(
            c.ok and c.tool_name in (
                'update_workflow_state', 'run_workflow',
                'save_workflow', 'save_as_new_workflow', 'deploy_workflow'
            )
        )
        -- the builder can also spawn a child run without a tool reporting it
        or exists (
            select 1 from bots_savedrun child
            where child.parent_builder_saved_run_id = c.saved_run_id
        ) as touched_workflow,
        bool_or(
            c.ok and c.tool_name in (
                'save_workflow', 'save_as_new_workflow', 'deploy_workflow'
            )
        ) as saved,
        bool_or(c.ok and c.tool_name = 'deploy_workflow') as deployed
    from calls c
    group by c.saved_run_id
),

steps as (
    select 1 as step_no, 'Prompts' as step, count(*) as prompts from per_prompt
    union all
    select 2, 'Tool attempted', count(*) filter (where attempted_tool) from per_prompt
    union all
    select 3, 'Workflow touched', count(*) filter (where touched_workflow) from per_prompt
    union all
    select 4, 'Saved', count(*) filter (where saved) from per_prompt
    union all
    select 5, 'Deployed', count(*) filter (where deployed) from per_prompt
)

select
    step_no,
    step,
    prompts,
    round(
        100.0 * prompts / nullif(max(prompts) over (), 0),
        1
    ) as pct_of_prompts
from steps
order by step_no

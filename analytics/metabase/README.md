# Builder analytics on Metabase

Metabase versions of the Gooey Builder analytics: live user interactions, the
builder prompts people are writing, and what those prompts produced.

These are plain SQL against the app database — no migration, no app code, and
nothing to deploy. Paste each file into a Metabase native question.

## Setup order

1. **`02_builder_tool_calls.sql` first**, saved as a **Model** named
   `Builder Tool Calls`. Everything else builds on it.
2. Open the saved model and note its card reference (`{{#123-builder-tool-calls}}`).
   Replace the `{{#02-builder-tool-calls}}` placeholder in files 03–06 with it.
3. `01_live_activity.sql` is standalone — it doesn't touch the model.
4. Add all six to one dashboard with a shared date filter wired to each card's
   `{{created_at}}`.

| File | What it answers |
|---|---|
| `01_live_activity.sql` | Who is doing what right now, every surface |
| `02_builder_tool_calls.sql` | **Model.** One row per builder tool call + success |
| `03_builder_prompt_outcomes.sql` | One row per prompt: text, tools, outcome, resulting workflow |
| `04_funnel.sql` | prompt → tool → workflow → saved → deployed drop-off |
| `05_tool_success_rates.sql` | Which builder tools fail, and how often |
| `06_failure_modes.sql` | Top errors, run-level and tool-level |

## How the tool calls are recovered

Builder tool calls aren't persisted anywhere queryable. Only
`functions/workflow_tools.py` writes `CalledFunction` rows, and the builder's LLM
tools don't go through it. The only record is the transcript in
`bots_savedrun.state->'final_prompt'`, where each assistant turn carries
`tool_calls` and every result comes back as a `role="tool"` message keyed by
`tool_call_id` (`recipes/VideoBots.py:llm_loop`).

`02_builder_tool_calls.sql` unnests that and pairs calls with results. Success
detection covers the three shapes the builder tools actually return:

| Shape | Example | Tool |
|---|---|---|
| bare `error` string | `{"error": "You can't update the root workflow"}` | save tools |
| structured `error` object | `{"error": {"msg": ..., "type": ...}}` | `run_workflow` |
| `success: false` | `{"success": false, "error": "Invalid platform"}` | deploy tool |

A call with no matching result stays `NULL`, not `false` — that's a run that died
mid-flight, not a tool that broke, and conflating them skews the success rates.
`run_workflow` returns the bare response with no `success` key at all, so
"parsed, and no error key" counts as success.

## Things to know before relying on this

**Refresh floor is 1 minute.** Metabase's dashboard auto-refresh options start at
1 minute; there is no 10s or 30s setting. (`#refresh=<seconds>` on the dashboard
URL is undocumented and not something to build a workflow on.) If sub-minute
freshness matters, that's the one thing Metabase can't do here.

**The model is expensive — always keep a date filter on it.** It unnests every
message of every builder transcript in range. Give `{{created_at}}` a default of
`Previous 24 hours` and turn on model caching before pointing it at a wide
window. There is no index on `bots_savedrun.surface`, so the date bound is what
keeps the scan sane (there *is* an index on `created_at`).

**It runs against whatever database Metabase points at.** If that's the primary
rather than a read replica, be careful with wide windows and short refresh
intervals — this is heavier than the usual Metabase question.

**Workflow slugs are hardcoded.** The app builds run URLs from
`page_cls.slug_versions` in Python; SQL has no access to that, so
`01_live_activity.sql` carries a literal workflow → slug table. If a recipe's
canonical slug changes, that table needs updating or its links will 404. The
lookup was generated from `recipes/*.py` and covers all 35 workflows.

**Postgres 15.** The JSON cast in the model is guarded by a regex rather than
`pg_input_is_valid`, which is Postgres 16+.

## Funnel semantics

Each funnel step counts prompts that got *at least* that far — "Saved" includes
prompts that went on to deploy. Testing each step in isolation would let a prompt
that saved without a separate edit/run step make "Saved" wider than "Workflow
touched", rendering an inverted funnel. `build_funnel` in
`daras_ai_v2/builder_analytics.py` was corrected to match.

## Relationship to `pages/BuilderAnalytics.py`

The Streamlit page computes the same numbers in Python
(`daras_ai_v2/builder_analytics.py`), where the transcript parsing is unit
tested. These queries are a port of that logic — if one changes, the other
should too.

What doesn't survive the port: the sub-minute live feed, the prompt-masking
toggle, and the per-prompt drilldown that renders each tool call's arguments and
errors inline. One small divergence: personal workspaces have a blank `name`
column and the app fills it in from the owner in Python, so these queries show
`Personal` instead of the owner's name.

## Verified against

All six queries were run on Postgres 16 against fixtures covering every
transcript shape: each of the three failure payloads, a `run_workflow` success
with no `success` key, a tool call with no result, a non-JSON tool result, a
`final_prompt` that is a string rather than an array, and a non-array
`tool_calls` value. Outcomes matched the Python classifier on all 11 fixture
prompts. The junk shapes are the ones worth keeping in mind if you edit the
model: a set-returning function is evaluated before the `WHERE` clause, so the
type guards have to live inside the `jsonb_array_elements(...)` argument, not
next to it.

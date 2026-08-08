# Builder analytics on Metabase

Metabase versions of the Gooey Builder analytics: live user interactions, the
builder prompts people are writing, and what those prompts produced.

These are plain SQL against the app database — no migration, no app code, and
nothing to deploy. Paste each file into a Metabase native question.

## Prerequisites

Metabase is **not** configured from this repo — the only reference in the
codebase is a bookmark link in `Home.py`. Before any of this works, someone with
Metabase admin needs to confirm the app's Postgres is registered under
**Settings → Admin → Databases**, and that your account has **native query**
(SQL editor) permission on it. See "Pointing Metabase at prod" below.

## Setup

Every file is standalone — paste it into a new SQL question and run. There is no
model to create first and no card references to fix up.

For each question, after pasting:

1. Open the variables sidebar (the `{{x}}` icon) and set `created_at` to
   **Field Filter → Bots Savedrun → Created At**, widget **Date filter**,
   default **Previous 24 hours**. Without this the `[[and {{created_at}}]]`
   clause is dropped and the query scans every builder run ever written.
   (`01_live_activity.sql` has a second optional filter, `surface`, mapped the
   same way to Bots Savedrun → Surface.)
2. Set the visualization: `04` → **Funnel** (Step = `step`, Measure = `prompts`;
   hide `step_no`). The rest are tables.
3. On table questions, set the `url` / `builder_run_url` / `workflow_url` columns
   to display as **Link** so they're clickable.
4. Save, then add all six to one dashboard. Add a dashboard **Date** filter and
   wire it to each card's `created_at` — this works precisely because each
   question carries its own field filter.
5. Dashboard → clock icon → **Auto-refresh: 1 minute** (the floor; see below).

| File | What it answers |
|---|---|
| `01_live_activity.sql` | Who is doing what right now, every surface |
| `02_builder_tool_calls.sql` | One row per builder tool call + whether it worked |
| `03_builder_prompt_outcomes.sql` | One row per prompt: text, tools, outcome, resulting workflow |
| `04_funnel.sql` | prompt → tool → workflow → saved → deployed drop-off |
| `05_tool_success_rates.sql` | Which builder tools fail, and how often |
| `06_failure_modes.sql` | Top errors, run-level and tool-level |

### Why these repeat the same CTE instead of sharing a model

An earlier version of this README had you save `02` as a Model and reference it
from `03`–`06` as `{{#123-builder-tool-calls}}`. That does not work with a
dashboard date filter: the `created_at` field filter would live inside the
*model*, so the dashboard filter on the downstream cards has nothing to bind to,
and the model's own default silently becomes a hard-coded window. If the model's
filter has no default at all, the optional clause is dropped when the card is
referenced and it scans the full table.

Metabase SQL snippets don't solve it either — snippets can't contain variables
or field filters, and the date bound has to be applied *inside* `builder_runs`,
before the transcript unnesting, or it is applied after the expensive part.

So the transcript CTE is duplicated across `03`–`06` on purpose. If you edit that
logic, edit it in all four (and in `daras_ai_v2/builder_analytics.py`).

## Pointing Metabase at prod

The queries read the app's own tables (`bots_savedrun`, `app_users_appuser`,
`workspaces_workspace`, `bots_messagethread`), so "seeing prod data" just means
Metabase has a connection to the prod application database.

* **Check first:** Admin → Databases. If the prod app DB is listed, pick it in
  the question editor and you're done — run
  `select count(*) from bots_savedrun where surface = 3;` as a smoke test.
* **If it isn't listed,** an admin adds it as a Postgres connection using the
  same coordinates the app uses (`PGHOST` / `PGPORT` / `PGDATABASE`, documented
  in `configuration.md`) — but with a **dedicated read-only user against a read
  replica**, not the app's own credentials against the primary:

  ```sql
  create user metabase_ro with password '...';
  grant connect on database <PGDATABASE> to metabase_ro;
  grant usage on schema public to metabase_ro;
  grant select on all tables in schema public to metabase_ro;
  alter default privileges in schema public grant select on tables to metabase_ro;
  ```

The read-replica part matters more than usual here: the transcript queries unnest
every message of every builder run in range, which is far heavier than a typical
Metabase question. Against the primary, on a short refresh interval, over a wide
window, this is enough load to notice.

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

**Always keep a date filter on these.** They unnest every message of every
builder transcript in range. Give `{{created_at}}` a default of `Previous 24
hours` and turn on question caching before pointing one at a wide window. There
is no index on `bots_savedrun.surface`, so the date bound is what keeps the scan
sane (there *is* an index on `created_at`).

**Workflow slugs are hardcoded.** The app builds run URLs from
`page_cls.slug_versions` in Python; SQL has no access to that, so
`01_live_activity.sql` carries a literal workflow → slug table. If a recipe's
canonical slug changes, that table needs updating or its links will 404. The
lookup was generated from `recipes/*.py` and covers all 35 workflows.

**Postgres 15.** The JSON cast is guarded by a regex rather than
`pg_input_is_valid`, which is Postgres 16+ only.

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
transcript CTE: a set-returning function is evaluated before the `WHERE` clause,
so the type guards have to live inside the `jsonb_array_elements(...)` argument,
not next to it.

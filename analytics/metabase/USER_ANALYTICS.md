# User Analytics tab

Four headline numbers plus one combined line chart, all driven by a single
time-range dropdown.

| Card | Query | Visualization |
|---|---|---|
| New users | `10_user_analytics_scorecards.sql` #1 | Number |
| New paid users | `10_user_analytics_scorecards.sql` #2 | Number |
| Ask Gooey queries | `10_user_analytics_scorecards.sql` #3 | Number |
| New deployments | `10_user_analytics_scorecards.sql` #4 | Number |
| Trend over time | `11_user_analytics_timeseries.sql` | Line (X=`bucket_start`, Y=`value`, Series=`metric`) |

`10_...` holds four separate queries because Metabase's Number visualization
renders only the first cell of a result — each needs its own card.

## The time range dropdown

This is the part with real Metabase mechanics, so in detail.

### On each question

1. In the native editor, type `{{range}}` anywhere in the SQL. The variables
   sidebar opens automatically.
2. **Variable type:** `Text`. (Not Date — a Date variable gives you Metabase's
   own date picker, not a list you control.)
3. **Filter widget label:** `Time range`
4. **How should users filter on this variable?** → `Dropdown list`
5. **Where do the values come from?** → `Custom list`, one per line:

   ```
   24 hours
   3 days
   7 days
   14 days
   30 days
   90 days
   ```

6. **Default filter widget value:** `7 days`. This is **required** — a native
   variable with no value makes the card error out rather than run unfiltered.

The values are passed straight to Postgres as an interval
(`now() - cast({{range}} as interval)`), which is why they read `3 days` and not
`Past 3 days`.

> **Version note:** "Custom list" as a values source for a *native query
> variable* needs Metabase 47+. On older versions the dropdown option only
> appears when the variable is a Field Filter mapped to a real column, and you'd
> have to use the Field Filter approach below instead.

### Wanting prettier labels

Metabase native variables don't support label/value pairs — the dropdown shows
exactly what it passes to SQL. If you want `Past 7 days` in the UI, map it in
SQL instead and use the pretty strings as your custom list:

```sql
cast(
    case {{range}}
        when 'Past 24 hours' then '24 hours'
        when 'Past 3 days'   then '3 days'
        when 'Past 7 days'   then '7 days'
        when 'Past 14 days'  then '14 days'
        when 'Past 30 days'  then '30 days'
        when 'Past 90 days'  then '90 days'
        else '7 days'
    end as interval
)
```

### Wiring one dropdown to every card

1. Add all five questions to a dashboard.
2. **Edit dashboard → Add a filter → Text or Category → Dropdown.**
3. Set the dashboard filter's own value list to the same custom list, and give
   it a default of `7 days`.
4. Click the filter, then on each card pick the `Time range` variable as the
   column to connect to. Do this for all five cards.

Now one dropdown drives the whole tab.

### The alternative: Field Filter + relative dates

If you'd rather have Metabase's native date UI (`Previous 30 days`, `Today`,
custom ranges, plus the "include this period" toggle), use a Field Filter instead:

```sql
where 1=1 [[and {{created_at}}]]
```

with the variable mapped to the table's `created_at` column, and connect a
dashboard **Date** filter to it. You get more flexibility and no interval-string
parsing, but you can't restrict users to a fixed set of options — which is what
you asked for, so the queries as written use the dropdown.

The two approaches don't mix well on one dashboard: a Date filter can't connect
to a Text variable. Pick one per tab.

## Metric definitions

Worth being explicit, because two of these have a defensible alternative reading:

**New users** — registered signups only. Anonymous sessions and disabled
(banned) accounts are excluded; counting anonymous sessions would inflate this
by a lot and isn't what "new users" means to anyone reading the dashboard.

**New paid users** — billing entities whose **first-ever** charged transaction
falls in the window. This deliberately excludes existing subscribers renewing —
verified against a fixture where a workspace that first paid 40 days ago and
renewed 2 hours ago is *not* counted. Keyed on `workspace_id`, because that's the
billing entity: a 5-person team that starts paying is one new paid customer, not
five. Swap to `user_id` in both files if you want it per individual.

Note `AppUser.is_paying` is marked deprecated in the model, which is why this
derives from transactions rather than reading that flag.

**Ask Gooey queries** — `SavedRun.surface = 3` (`builder_prompt`, shown as "Ask
Prompt" in the admin). Counts prompts, not conversations; a 5-turn conversation
is 5 queries. Group by `message_thread_id` instead if you want conversations.

**New deployments** — one row per `BotIntegration` created. This counts
deployments *created*, including ones later abandoned or never messaged.

## Suggested additional metrics

Ordered by how much they'd add to this tab, all available from tables the DB
already has.

**Would round out the funnel this tab implies:**

1. **Activation rate** — new users who ran at least one workflow, over new users.
   Signups mean little without it. (`app_users_appuser` ⋈ `bots_savedrun`)
2. **Anonymous → registered conversions** — `upgraded_from_anonymous_at` is
   already a column, so this is nearly free.
3. **Paid conversion rate** — new paid users / new users, same window.
4. **Active users (DAU / WAU)** — distinct `uid` with any run in the period.
   The single best engagement number, and the natural denominator for the rest.

**Usage depth:**

5. **Total runs, split by surface** — Run / API / Deployment / Ask, as a stacked
   area. Shows whether growth is UI, API, or bot traffic.
6. **Runs per active user** — separates "more users" from "more usage".
7. **Ask Gooey → deployment conversion** — of users who asked, how many ended up
   deploying. Ties this tab to the builder funnel.
8. **Messages through deployments** (`bots_message`) — deployments *created* is a
   vanity number; messages handled is the real one.

**Money:**

9. **Revenue** — `sum(charged_amount)/100` in the window, split by
   `reason` (new subs vs renewals vs auto-recharge).
10. **Credits consumed** — `sum(price)` on runs, the cost side against revenue.

**Health:**

11. **Run error rate** — share of runs with `error_msg <> ''`. Belongs on any
    dashboard someone watches daily.
12. **p50 / p95 run time** — `run_time` percentiles; catches slow regressions.

Deployments by platform (WhatsApp / Slack / Web / Telegram) is also a one-liner
if you want a breakdown pie next to the deployment count.

Say which you want and I'll write them in the same style, driven by the same
`{{range}}` dropdown.

## Notes

**Timezone.** `date_trunc` uses the database session timezone, which Metabase
sets from **Admin → Localization → Report timezone**. If daily buckets need to
land on IST midnight, set that; or force it per query with
`date_trunc(b.bucket, u.created_at at time zone 'Asia/Kolkata')`.

**Bucket size** is derived from the range — hourly up to 3 days, daily beyond —
rather than being a second dropdown, since 90 days of hourly buckets is 2,160
points of noise. To make it an explicit control, swap the `bucket` expression in
`params` for a `{{bucket}}` variable with values `hour` / `day` / `week`.

**Zero-filling.** The time series generates its buckets with `generate_series`
and left-joins the metrics on. Without it, a metric with no rows in a bucket has
no point at all there and the line is drawn straight across the gap, which reads
as "flat" rather than "zero".

**Cost.** These are cheap — plain counts against indexed `created_at` columns,
nothing like the JSONB transcript unnesting in the builder queries. Safe to put
on a short dashboard refresh.

## Verified against

Both files were run on Postgres 16 against fixtures covering: registered vs
anonymous vs disabled signups, in-window and out-of-window signups, a workspace
whose first payment is in-window, a workspace that first paid 40 days ago and
renewed inside the window (correctly excluded), a zero-charge deduct row
(ignored), and deployments in and out of window. The time series totals match
the scorecards exactly at the same range, and bucket counts were checked at both
hourly (25 buckets for 24 hours) and daily (8 buckets for 7 days) resolution.

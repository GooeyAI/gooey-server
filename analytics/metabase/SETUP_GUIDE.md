# Building the User Analytics dashboard in Metabase

Step by step, from an empty Metabase to a working dashboard with one time-range
dropdown driving five cards.

Menu wording drifts between Metabase versions — this is written against v47+.
If a label doesn't match exactly, the shape of the flow is still right.

Total time: about 30 minutes, most of it pasting SQL.

---

## Phase 0 — Before you start (2 min)

1. **Check the database is connected.** Top right gear → **Admin settings** →
   **Databases**. The prod app Postgres should be listed. If it isn't, that's a
   prerequisite — see "Pointing Metabase at prod" in `README.md`.
2. **Check you can write SQL.** Click **+ New** (top right). If **SQL query**
   isn't in the menu, your account lacks native-query permission on that
   database and an admin needs to grant it.
3. **Smoke test.** **+ New → SQL query**, pick the database, run:

   ```sql
   select count(*) from bots_savedrun where surface = 3;
   ```

   A number means everything downstream will work. An error about the relation
   not existing means you're pointed at the wrong database.

---

## Phase 1 — Make a collection (1 min)

**+ New → Collection**, name it `Gooey Analytics`.

Worth doing before you create anything: five loose questions in "Our analytics"
get lost fast, and a collection is also the unit Metabase uses for permissions
later.

---

## Phase 2 — Create the four scorecard questions (12 min)

Do the first one slowly; the other three are the same five clicks.

### 2.1 — The first card, in full

1. **+ New → SQL query**, pick the prod database.
2. Open `10_user_analytics_scorecards.sql` and copy **query 1 only** — the block
   under `1. New users`, ending at its semicolon. Paste it in.
3. The moment `{{range}}` appears in the editor, the **variables sidebar** opens
   on the right. Set:
   - **Variable type:** `Text`
   - **Filter widget label:** `Time range`
   - **How should users filter on this variable?** → `Dropdown list`
   - **Where do the values come from?** → `Custom list`, then one per line:
     ```
     24 hours
     3 days
     7 days
     14 days
     30 days
     90 days
     ```
   - **Default filter widget value:** `7 days`

   > The default is **not optional**. A native variable with no value makes the
   > card fail to run rather than run unfiltered. This is the single most common
   > thing to get stuck on.

4. Hit **Run** (▶). You should get a single number.
5. **Visualization** (bottom left) → **Number**.
6. **Save** → name it `New users` → into the `Gooey Analytics` collection.
   When asked "add this to a dashboard?", choose **Not now** — the dashboard
   comes later.

### 2.2 — Repeat for the other three

Same steps, one query each:

| Query in the file | Save as |
|---|---|
| `2. New paid users` | `New paid users` |
| `3. Ask Gooey queries` | `Ask Gooey queries` |
| `4. New deployments` | `New deployments` |

Card names become the tile labels on the dashboard, so keep them short and
exactly as above.

Every one of the four needs its own `{{range}}` variable configured the same
way. Metabase does not share variable settings between questions — there's no
way around doing it four times.

---

## Phase 3 — Create the line chart (5 min)

1. **+ New → SQL query**, same database.
2. Paste all of `11_user_analytics_timeseries.sql`.
3. Configure `{{range}}` exactly as in Phase 2.1 step 3 (same type, same list,
   same default).
4. **Run.** You should get three columns: `bucket_start`, `metric`, `value`.
5. **Visualization → Line.** Then open the settings (gear next to the
   visualization picker) and set:
   - **X-axis:** `bucket_start`
   - **Y-axis:** `value`
   - **Series / Break out by:** `metric`

   If you get one flat line instead of four, the series breakout isn't set —
   that's the fix.
6. Optional but nice: **Settings → Axes → Y-axis → Auto-format**, and under
   **Display**, turn on **Show values on data points** only if the buckets are
   sparse; on 90 days of daily data it's unreadable.
7. **Save** as `User growth over time` into `Gooey Analytics`.

---

## Phase 4 — Build the dashboard (5 min)

1. **+ New → Dashboard**, name it `User Analytics`, put it in
   `Gooey Analytics`.
2. Click the **+** (add questions) in the top bar. Add all five, in order:
   the four scorecards, then the line chart.
3. Arrange by dragging the bottom-right corner of each card:
   - Four scorecards **in one row across the top**, each a quarter width.
   - The line chart **full width underneath**.
4. **Save.**

Metabase snaps to an 18-column grid, so a quarter-width tile is roughly 4–5
columns. Getting all four on one row takes a bit of dragging.

---

## Phase 5 — The one dropdown that drives everything (5 min)

This is the part that makes it a dashboard rather than five separate questions.

1. **Edit** the dashboard (pencil icon).
2. Click the **filter icon** (funnel) in the top bar → **Add a filter**.
3. Choose **Text or Category** → **Dropdown**.
4. In the filter settings on the right:
   - **Label:** `Time range`
   - **How should people filter on this?** → `Dropdown list` →
     **Custom list**, same six values as before
   - **Default value:** `7 days`
5. **Connect it to every card.** With the filter still selected, each card shows
   a dropdown reading *"Select…"*. On **each of the five cards**, pick the
   `Time range` variable.

   > Miss one card and it silently keeps its own default while the others move.
   > That's the second most common thing to get stuck on, and it looks like a
   > data bug rather than a wiring bug. Count them: five connections.

6. **Save.**

---

## Phase 6 — Verify it actually works (3 min)

Three checks, in order:

1. **The dropdown moves everything.** Switch `Time range` from `7 days` to
   `24 hours`. All five cards should change — including the line chart, which
   should also switch from daily to hourly buckets (it derives the bucket from
   the range).
2. **The cards agree with each other.** For a given range, the line chart's
   total for a metric should equal that metric's scorecard. Hover the line
   series and add up, or eyeball a quiet range like `24 hours`. This is the
   check that catches a card whose filter isn't connected — the queries are
   written so these two numbers must match.
3. **Sanity-check one number against reality.** `New deployments` over
   `30 days` should be a number someone on the team can confirm. If it's wildly
   off, the metric definition probably doesn't match your mental model — see
   "Metric definitions" in `USER_ANALYTICS.md`, particularly for *new paid
   users*, which counts first-ever payments and deliberately excludes renewals.

---

## Phase 7 — Polish (optional)

- **Auto-refresh:** dashboard → clock icon → pick an interval. 1 minute is the
  floor Metabase offers.
- **Caching:** if the dashboard is shared widely, **Admin → Performance** →
  cache results. These queries are cheap (plain counts on indexed `created_at`),
  so this is about politeness to the database, not necessity.
- **Subscriptions:** the sharing icon → **Subscriptions** sends a weekly email
  or Slack digest of the tab. Genuinely useful for a growth dashboard.
- **Card titles:** hover a card → pencil → give it a clearer title or subtitle
  than the question name if you want.
- **Permissions:** collection → **…** → **Permissions**, if this shouldn't be
  visible to everyone with a Metabase login.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Card errors with "You'll need to pick a value for Time range" | The variable has no default | Set **Default filter widget value** to `7 days` on that question |
| Variable sidebar offers only a search box, no dropdown | Metabase older than v47, or values source isn't set | Set **Where do the values come from** → **Custom list**; on older versions use the Field Filter approach in `USER_ANALYTICS.md` |
| Dashboard filter won't connect to a card | Type mismatch — a **Date** filter can't bind to a **Text** variable | Make the dashboard filter **Text or Category** |
| One card ignores the dropdown | That card wasn't connected in Phase 5 step 5 | Edit → click the filter → set the card's dropdown to `Time range` |
| Line chart shows a single line | Series breakout not set | Visualization settings → break out by `metric` |
| Line chart has gaps or flat stretches | Expected — quiet buckets are zero-filled by design, so a flat line at 0 is real, not missing data | Nothing to fix |
| Daily buckets land at the wrong hour | Report timezone | **Admin → Localization → Report timezone**, or force it per query (see `USER_ANALYTICS.md`) |
| `relation "bots_savedrun" does not exist` | Wrong database selected | Re-pick the prod app DB in the query editor |
| Numbers look too high | `New users` includes anonymous? It shouldn't — the query excludes them. Check you pasted the right query block | Re-copy query 1 from the file |

---

## Adding more cards later

Every metric in the "Suggested additional metrics" list in `USER_ANALYTICS.md`
follows the same pattern: new SQL question with a `{{range}}` Text variable →
save to `Gooey Analytics` → add to the dashboard → connect the filter.

The only step that's easy to forget is the last one.

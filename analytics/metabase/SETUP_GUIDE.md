# Building the User Analytics dashboard in Metabase

Step by step, from an empty Metabase to a dashboard laid out like the Metabase
"E-commerce insights" example: tabs across the top, a filter row, section
headings, trend cards with period-over-period comparison, a goal bar, and a
combo chart.

Menu wording drifts between Metabase versions — this is written against v47+.
If a label doesn't match exactly, the shape of the flow is still right.

Total time: about 45 minutes, most of it pasting SQL.

---

## What you're building

```
┌─ User Analytics ─┬─ Workflows ─┬─ Deployments ─┐   <- dashboard tabs
│                                                     
│  [ Time range ▾ ]                                <- filter row
│                                                     
│  ## Overall user growth                          <- heading card
│                                                     
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐    <- 4 Trend cards
│  │ 907    │ │ 43     │ │ 2,104  │ │ 61     │       big number +
│  │ ↑11.7% │ │ ↑ 7.5% │ │ ↓ 3.2% │ │ ↑22.0% │       % vs previous period
│  └────────┘ └────────┘ └────────┘ └────────┘       
│                                                     
│  ┌──────────┐ ┌──────────────────────────────┐  <- Progress + Combo
│  │ goal bar │ │  bars + line, dual axis      │     
│  └──────────┘ └──────────────────────────────┘     
```

| Card | Query | Visualization |
|---|---|---|
| New users | `10_..._scorecards.sql` #1 | **Trend** |
| New paid users | `10_..._scorecards.sql` #2 | **Trend** |
| Ask Gooey queries | `10_..._scorecards.sql` #3 | **Trend** |
| New deployments | `10_..._scorecards.sql` #4 | **Trend** |
| Growth over time | `11_..._timeseries.sql` | **Combo** |
| Monthly goal | `12_..._goal.sql` | **Progress** |

---

## Phase 0 — Before you start (2 min)

1. **Database connected?** Gear → **Admin settings** → **Databases**. The prod
   app Postgres should be listed. If not, see "Pointing Metabase at prod" in
   `README.md`.
2. **Can you write SQL?** Click **+ New**. If **SQL query** isn't there, your
   account lacks native-query permission and an admin must grant it.
3. **Smoke test.** **+ New → SQL query**, pick the database, run:

   ```sql
   select count(*) from bots_savedrun where surface = 3;
   ```

   A number means everything downstream works. "Relation does not exist" means
   you're on the wrong database.

---

## Phase 1 — Make a collection (1 min)

**+ New → Collection**, name it `Gooey Analytics`.

Six loose questions in "Our analytics" get lost fast, and the collection is the
unit Metabase uses for permissions later.

---

## Phase 2 — The four trend cards (15 min)

Do the first slowly; the rest are the same clicks.

### 2.1 — First card, in full

1. **+ New → SQL query**, pick the prod database.
2. From `10_user_analytics_scorecards.sql`, copy **query 1 only** — the block
   under `1. New users`, ending at its semicolon. Paste it.
3. `{{range}}` in the editor opens the **variables sidebar**. Set:
   - **Variable type:** `Text`
   - **Filter widget label:** `Time range`
   - **How should users filter on this variable?** → `Dropdown list`
   - **Where do the values come from?** → `Custom list`:
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
   > place to get stuck.

4. **Run** (▶). You should get **two rows** — previous period and current:

   ```
   period_start              | new_users
   2026-07-30 …              | 812
   2026-08-06 …              | 907
   ```

   Two rows is the point. Metabase's Trend card computes the % change from the
   last two rows; a single-row result can only ever render a plain number.

5. **Visualization → Trend.** It should immediately show the big number with
   "▲ 11.7% vs. previous period" beneath.
6. Optional: the visualization settings let you switch the **Comparison** to
   *Previous value* / *Previous period* / a custom value, and set whether up is
   good (green) or bad (red). For *Ask Gooey queries* leave up = good; there's
   no metric here where a rise is bad.
7. **Save** as `New users` into `Gooey Analytics`. Choose **Not now** when asked
   about adding to a dashboard.

### 2.2 — Repeat for the other three

| Query in the file | Save as |
|---|---|
| `2. New paid users` | `New paid users` |
| `3. Ask Gooey queries` | `Ask Gooey queries` |
| `4. New deployments` | `New deployments` |

Card names become the tile labels, so keep them exactly as above.

Each needs its own `{{range}}` variable configured the same way — Metabase
doesn't share variable settings between questions, so it's four times over.

---

## Phase 3 — The combo chart (7 min)

1. **+ New → SQL query**, paste all of `11_user_analytics_timeseries.sql`.
2. Configure `{{range}}` exactly as above.
3. **Run.** Five columns: `bucket_start` plus one per metric. This wide shape is
   what makes a combo chart possible — each column is its own series, so display
   type and axis can differ per metric.
4. **Visualization → Combo.**
5. Settings (gear) → **Data**:
   - **X axis:** `bucket_start`
   - **Y axis:** tick all four count columns
6. Settings → **Series** — click each series and set:

   | Series | Display | Axis |
   |---|---|---|
   | `ask_gooey_queries` | Line | **Right** |
   | `new_users` | Bar | Left |
   | `new_paid_users` | Bar | Left |
   | `new_deployments` | Bar | Left |

   The right axis matters. Ask Gooey queries run one to two orders of magnitude
   above new paid users; on a shared axis the small series flatten onto zero and
   the chart tells you nothing.

7. **Save** as `Growth over time`.

---

## Phase 4 — The goal card (4 min)

1. **+ New → SQL query**, paste **query 1** from `12_user_analytics_goal.sql`
   (new paid users, month to date). No `{{range}}` variable on this one.
2. **Run** — a single number.
3. **Visualization → Progress.** In settings, set **Goal** to your monthly
   target. The goal lives in the viz settings, not the SQL, so changing the
   target later is a two-click edit.
4. **Save** as `New paid users — monthly goal`.

This card deliberately ignores the time-range dropdown and uses month-to-date. A
progress bar only means something against a fixed target period — if it followed
the dropdown, picking "24 hours" would show 3% of a monthly goal, which reads as
failure rather than "it's the 1st".

---

## Phase 5 — Assemble the dashboard (6 min)

1. **+ New → Dashboard**, name it `Gooey Analytics`, save into the collection.
2. **Add tabs.** In edit mode, click **+** next to the dashboard title (or
   **Add tab** in the toolbar). Name the first tab **User Analytics**. Add more
   later for Workflows / Deployments — tabs are per-dashboard, and filters can
   be applied per tab.
3. **Add a heading.** In edit mode, the toolbar has a **text/heading** icon.
   Add a **Heading** card reading `Overall user growth`. Headings are what make
   the screenshot's layout read as sections rather than a wall of tiles.
4. **Add the six questions** via the **+** (add question) button.
5. **Arrange** by dragging each card's bottom-right corner:
   - Four trend cards in **one row**, each a quarter width.
   - Progress card and combo chart on the **next row** — narrow left, wide right.
6. **Save.**

Metabase snaps to an 18-column grid, so a quarter-width tile is roughly 4–5
columns. Getting four onto one row takes some dragging.

---

## Phase 6 — The filter row (5 min)

1. **Edit** the dashboard → **filter icon** (funnel) → **Add a filter**.
2. **Text or Category** → **Dropdown**.
3. Filter settings:
   - **Label:** `Time range`
   - **Values** → `Custom list`, same six values
   - **Default value:** `7 days`
4. **Connect it to every card.** With the filter selected, each card shows a
   *"Select…"* dropdown. On **each of the five cards that use `{{range}}`**,
   pick the `Time range` variable.

   > Miss a card and it silently keeps its own default while the others move.
   > It looks like a data bug, not a wiring bug. Count them: five connections.
   > The Progress card is the one that intentionally stays unconnected.

5. **Save.**

### About the other filters in the screenshot

The e-commerce example has four filters (Vendor, Date Range, Category, Location)
because every card there shares those dimensions. For this tab, **time is the
only dimension all four metrics genuinely share** — new users have no platform,
deployments have no workflow. Adding a Platform dropdown here would leave three
of four cards ignoring it, which is worse than not having it.

A filter row like the screenshot's earns its place on the *other* tabs:
Workflows (workflow, surface, workspace) and Deployments (platform, workspace).
Build those tabs and their filters will have something to bind to.

The one extra filter that does make sense here is an **account scope** dropdown
(`All` / `Exclude team`), since team accounts inflate signups and Ask Gooey
counts. Say the word and I'll add it to the queries.

---

## Phase 7 — Verify (3 min)

1. **The dropdown moves everything.** Switch `Time range` from `7 days` to
   `24 hours`. All five connected cards should change, and the combo chart
   should also switch from daily to hourly buckets.
2. **The cards agree.** For a given range, each metric's column total in the
   combo chart should equal that metric's trend card *current* value. The
   queries are written so these must match — a mismatch means a card isn't
   wired. (Verified on fixtures: 4 / 1 / 11 / 2 at 7 days, both ways.)
3. **Sanity-check one number.** `New deployments` over `30 days` should be a
   figure someone on the team can confirm. If it's wildly off, the definition
   probably doesn't match your mental model — see "Metric definitions" in
   `USER_ANALYTICS.md`, especially *new paid users*, which counts first-ever
   payments and excludes renewals.

---

## Phase 8 — Polish (optional)

- **Auto-refresh:** clock icon → interval. 1 minute is Metabase's floor.
- **Card info tooltips:** the screenshot's ⓘ next to "Number of orders" is a
  card **description** — hover a card in edit mode → pencil → add one. Worth it
  for *new paid users*, whose definition isn't obvious from the title.
- **Subscriptions:** sharing icon → **Subscriptions** for a weekly email or
  Slack digest.
- **Caching:** **Admin → Performance**. These queries are cheap (plain counts on
  indexed `created_at`), so this is politeness to the DB, not necessity.
- **Permissions:** collection → **…** → **Permissions**.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| "You'll need to pick a value for Time range" | Variable has no default | Set **Default filter widget value** to `7 days` |
| Trend card shows a number but no % change | Query returned one row | You pasted a single-period query — use `10_..._scorecards.sql`, which returns two rows |
| Trend comparison says "vs. previous period" but the period looks wrong | Expected — the comparison window equals the selected range | Pick a different range; 7 days compares against the 7 days before |
| Variable sidebar offers only a search box | Metabase < v47, or values source unset | Set **Custom list**; on older versions use the Field Filter approach in `USER_ANALYTICS.md` |
| Dashboard filter won't connect to a card | Type mismatch — a **Date** filter can't bind a **Text** variable | Make the dashboard filter **Text or Category** |
| One card ignores the dropdown | Not connected in Phase 6 | Edit → click filter → set that card's dropdown |
| Combo chart is unreadable, small series flat at zero | All series on one axis | Move `ask_gooey_queries` to the **right** axis |
| Combo chart shows one series | Y-axis columns not all ticked | Settings → Data → tick all four |
| Chart has flat stretches | Expected — quiet buckets are zero-filled by design | Nothing to fix |
| Daily buckets land at the wrong hour | Report timezone | **Admin → Localization → Report timezone** |
| `relation "bots_savedrun" does not exist` | Wrong database | Re-pick the prod app DB |

---

## Adding more cards later

Every metric in "Suggested additional metrics" in `USER_ANALYTICS.md` follows
the same pattern: new SQL question with a `{{range}}` Text variable → save to
`Gooey Analytics` → add to the dashboard → connect the filter.

For a trend card, copy the `params` / `periods` CTE from
`10_user_analytics_scorecards.sql` and swap the counting subquery. That two-row
shape is the only thing the Trend visualization needs.

The step that's easy to forget is still the last one: connect the filter.

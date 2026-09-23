# Typography audit: where the codebase drifts from Inter

Audited at master `b3489fd86` (merge of `feat/v2-layout-public-release`), 2026-09-16.
Scope: every `font-family`, `font-size`, `font-weight`, `letter-spacing` and font-loading
declaration in `gooey-gui/app/**/*.css`, `gooey-gui/app/**/*.tsx`, Python render code
(`daras_ai_v2/`, `widgets/`, `recipes/`, `routers/`, `gooey_gui/`) and `templates/`.
`node_modules`, build output and `.claude/worktrees` were excluded.

## 1. Summary

The design system names two faces, **Inter** (UI) and **Domine** (display headings), and
app.css defines them as tokens (`--gooey-font-ui`, `--gooey-font-heading`). But Inter is
**opt-in**: it only applies inside four marker classes. Everything else on the site still
renders the legacy pair, **basiercircle** for body text and **Avenir LT 85 Heavy** for
headings, bold text and table headers. Today only one recipe (Copilot, `VideoBotsPageV2`) is on
layout v2, so most pages are a mix: an Inter navigation rail beside basiercircle content.

Beyond the family split, there is no type scale. Sizes are written ad hoc in px, rem, em and
percent across 13 CSS files and 46 inline Python sites, weights are hand-picked per component,
and "uppercase eyebrow" labels have four different letter-spacing treatments.

The five findings that matter most:

| # | Finding | Where | Impact |
|---|---------|-------|--------|
| 1 | BulkProgressCard hardcodes Avenir in five rules, including a Wix-export family name that no `@font-face` declares | `BulkProgressCard.css:173,234,356,430,438` | Bulk-run card is Avenir inside the Inter v2 shell |
| 1b | A v2 recipe's Examples tab redirects to the v1 Explore page | `routers/root.py:386-414` | One click from the Copilot Run tab lands on Avenir titles and basiercircle body |
| 2 | Table headers and `.streamlit-like-btn` are on Avenir and missing from the v2 override list | `custom.css:186-190`, `custom.css:16`; override at `app.css:497-500` | Any Bootstrap table or copy button in v2 renders Avenir |
| 3 | Headings inherit `font-weight: 400`, written for a single-weight heavy face; under Inter they render Regular | `custom.css:192-252` | Home, History and Workspace `h1`/`h4` are light Inter unless each component re-specifies |
| 4 | Three monospace stacks and no `--gooey-font-mono` token | Bootstrap default, `BulkProgressCard.css:339`, bare `monospace` in 4 places | Code, IDs and secrets render in different faces |
| 5 | The v2 top bar renders outside the `v2-app-shell` marker, and its heading uses `font: inherit` | `daras_ai_v2/base_v2.py:141-153`, `RecipeTopBar.css:820-825` | The recipe title "Agent Builder" at the top of every v2 page computes to basiercircle, not Inter |

Every finding above was confirmed against the running app with Puppeteer: computed
`font-family` and `font-weight` were read off the live DOM, and the screenshots in the
published artifact come from the same capture.

## 1a. Site census: what actually renders

A headless Chrome pass over 15 page loads read the computed `font-family` off every visible
text node. Element counts per family (signed-in pages could not be captured; `/new/`
redirects to login when signed out):

| Page | Inter | basiercircle | Avenir | mono | other | distinct sizes |
|------|------:|-------------:|-------:|-----:|------:|---------------:|
| Explore | 7 | 113 | 23 | 0 | 0 | 4 |
| Copilot v2, Run | 25 | 6 | 0 | 50 | 0 | 4 |
| Copilot v2, API | 22 | 6 | 0 | 67 | 0 | 7 |
| Copilot v2, Examples (redirects to Explore) | 7 | 78 | 29 | 0 | 0 | 5 |
| Copilot v2, Integrations | 15 | 6 | 0 | 0 | 0 | 4 |
| Compare LLM (v1) | 7 | 38 | 12 | 19 | 0 | 7 |
| Doc Search (v1) | 7 | 58 | 9 | 0 | 3 | 7 |
| Bulk Runner (v1) | 7 | 60 | 6 | 0 | 1 | 6 |
| Bulk Runner, completed run | 7 | 61 | 14 | 0 | 1 | 9 |
| Login (Jinja) | 0 | 30 | 7 | 0 | 6 | 4 |
| 404 (Jinja) | 0 | 30 | 7 | 0 | 0 | 3 |
| Copilot v2, 390px | 27 | 1 | 0 | 50 | 0 | 4 |
| Explore, 390px | 7 | 114 | 23 | 0 | 0 | 4 |
| Compare LLM, 390px | 7 | 37 | 12 | 19 | 0 | 7 |

What the census adds to the file-level audit:

- **Only three pages are majority Inter**, all Copilot v2 tabs inside the shell. On every
  other page the seven Inter elements are the navigation rail and nothing else.
- **The six basiercircle elements on every v2 tab are the top bar**: title, byline, the
  About and How it works tabs, the cost readout and the Run label.
- **A v2 recipe's Examples tab is a v1 page.** `routers/root.py:386-414` redirects it to
  `/explore/?workflow=...`, so the only v2 recipe hands users to Avenir and basiercircle one
  click from its Run tab.
- **Jinja pages have zero Inter.** Login and 404 use the old header nav in basiercircle,
  Avenir headings, and Roboto on the Firebase UI sign-in buttons.
- **Sizes compound.** The completed bulk run has nine distinct computed sizes including
  13.12px, 13.6px, 15.68px and 24.8px, which are `smaller` and `em` chains, not design
  values. The 13.333px on Compare LLM is the browser default on form controls that do not
  inherit.
- **"other"** is Roboto (Firebase UI) and the Uppy file picker's own stack.

The x-ray screenshots that outline each family on each page are in the published artifact.

## 2. Inventory: what fonts exist and how they load

### 2.1 Families declared

| Family | Declared in | Source | Weights | Used by |
|--------|-------------|--------|---------|---------|
| Inter | `app.css:386-408` | fonts.gstatic.com, Inter v20 variable, latin + latin-ext only | 100-900 | `--gooey-font-ui` |
| Domine | `app.css:410-432` | fonts.gstatic.com, v25 variable, latin + latin-ext | 400-700 | `--gooey-font-heading` |
| basiercircle | `custom.css:125-139` | self-hosted `.otf` next to the CSS | 400 (regular), 700 (medium file) | `body`, `.gui-md-container strong` |
| avenir-lt-w05_85-heavy | `custom.css:120-123` | `static.parastorage.com` (Wix CDN), no `font-display` | single weight | `h1`-`h6`, `strong`, `.bold`, `.semibold`, `th`, `.streamlit-like-btn`, BulkProgressCard |
| avenir-lt-w01_85-heavy1475544 | nowhere | not loaded | none | BulkProgressCard first choice, silently falls through |
| Space Grotesk | commented out `custom.css:1` | not loaded | none | still listed as fallback in `custom.css:16,190` and BulkProgressCard |
| Font Awesome 7 Pro | kit script `root.tsx:78` | kit.fontawesome.com | icon | `widgets/workflow_search.py:272` hardcodes the family for a `::before` glyph |

### 2.2 Loading problems

- **`custom.css:3`** imports a `.woff2` URL with `@import url(...)`. That is a stylesheet import
  of a binary font. Browsers fetch it, fail to parse it, and the `@font-face` at line 120
  fetches it again. It is a wasted request and should be deleted.
- **Avenir comes from a Wix CDN** with no `font-display`, no `unicode-range` and no
  integrity. It is a third-party runtime dependency for the site's heading face.
- **Inter and Domine cover Latin only.** Gooey serves Hindi, Arabic, Cyrillic and other
  scripts. Text outside `U+0000-024F` falls to basiercircle, then to the platform sans. No
  `<link rel=preconnect>` or `preload` exists in `root.tsx`, so first paint waits on a
  cold connection to gstatic.
- **Two Bootstrap versions.** `app.tsx:40` loads 5.2.3, `templates/base.html:15` and
  `templates/auto_payment_failed_email.html:8` load 5.3.0. 5.3 adds `.fw-medium`, which
  `HomePage.css:313-320` notes it had to hand-roll.
- **Django templates** (`templates/base.html:17-18`) load the site CSS through the
  `/static/styles` mount in `server.py:66`, so login and error pages get basiercircle and
  Avenir like a v1 page. They never get Inter, since none of the marker classes exist there.
  The login page additionally pulls Roboto through the Firebase UI stylesheet.

## 3. How the cascade works today

```
bootstrap.min.css        body { font-family: var(--bs-body-font-family) }   (system-ui stack)
custom.css:141           body { font-family: "basiercircle", sans-serif }
custom.css:180-190       h1..h6, th, strong, .bold, .semibold { font-family: avenir... }
app.css:241              .gui-md-container strong { font-family: basiercircle }
app.css:485-491          .v2-app-shell, .nav-sidebar, .gooey-ds-page, .ask-gooey-page
                           { font-family: var(--gooey-font-ui) }            (Inter)
app.css:497-500          :is(shell) :is(h1..h6, strong, .bold, .semibold)
                           { font-family: var(--gooey-font-ui) }            (Inter)
app.css:504-507          .v2-app-shell .v2-about h1, .ask-gooey-title { Domine }
```

The four marker classes are applied at:

| Marker | Applied by | Renders in |
|--------|------------|------------|
| `v2-app-shell` | `daras_ai_v2/base_v2.py:153` | Copilot recipe only (`all_pages_v2.py`). The top bar placeholder at `:141` is a sibling, not a child, so the bar is outside the scope |
| `nav-sidebar` | `NavigationSidebar/index.tsx:172` | every `sidebar_page_wrapper` page, v1 and v2 (`routers/root.py:843`) |
| `gooey-ds-page` | `HomePage/index.tsx:26`, `HistoryPage.tsx:47`, `RunGrid.tsx:14` | v1 shell |
| `ask-gooey-page` | `AskGooeyNew.tsx:172` | its own route |

Consequences:

- Every page shows an Inter rail. Every v1 recipe page shows basiercircle body text and
  Avenir headings next to it. That is the most visible inconsistency on the site.
- The override at `app.css:497` lists `h1..h6, strong, .bold, .semibold` but **not**
  `.table > thead > tr > th` or `.streamlit-like-btn`, which `custom.css` also hands to
  Avenir. Bootstrap tables render in v2 through `managed_secrets/widgets.py:35`,
  `daras_ai_v2/manage_api_keys_widget.py:39`, `workspaces/views.py:552,726` and
  `gooey_gui/components/common.py:734`. `.streamlit-like-btn` is used by nine Python
  widgets including the copy-to-clipboard button.
- `.gui-md-container strong` at `app.css:241` means markdown bold in v1 is basiercircle
  medium while HTML `<strong>` outside markdown is Avenir heavy. v1 has two bold faces.
- Python code has no way to ask for Inter except by adding `className="gooey-ds-page"`
  to a wrapper. Nothing documents that.

## 4. Family drift, file by file

### 4.1 Hardcoded families that bypass the tokens

| File:line | Declaration | Should be |
|-----------|-------------|-----------|
| `gooey-gui/app/components/bulkProgress/BulkProgressCard.css:173` | `avenir-lt-w01_85-heavy1475544, avenir-lt-w05_85-heavy, "Space Grotesk", sans-serif` on `.bulk-progress-headline` | `var(--gooey-font-ui)` + explicit weight |
| `BulkProgressCard.css:234` | same, on `.bulk-progress-current strong`, with `font-weight: 400` | inherit family, weight 600 |
| `BulkProgressCard.css:356` | same, on `.bulk-progress-last-completed` | token |
| `BulkProgressCard.css:430` | same, on `.bulk-progress-stat-label` | token |
| `BulkProgressCard.css:438` | same, on `.bulk-progress-stat-value` | token |
| `BulkProgressCard.css:339` | `ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace` | `var(--gooey-font-mono)` (new token) |
| `gooey-gui/app/components/AskGooeyNew.css:154` | `font-family: Inter, sans-serif` on the textarea | `var(--gooey-font-ui)`; the literal skips the basiercircle fallback the token defines |
| `gooey-gui/app/styles/app.css:241` | `.gui-md-container strong { font-family: basiercircle }` | delete once Inter is global; today it creates the v1 double-bold |
| `gooey-gui/app/styles/custom.css:16` | `.streamlit-like-btn` on Avenir | add to the v2 override list now, token later |
| `gooey-gui/app/styles/custom.css:186` | `.table > thead > tr > th` on Avenir | same |
| `gooey-gui/app/components/CodeEditor.tsx:167` | `fontFamily: "monospace"` | mono token |
| `daras_ai_v2/doc_search_settings_widgets.py:67` | `"fontFamily": "monospace"` | `.font-monospace` class |
| `managed_secrets/widgets.py:149` | `fontFamily="monospace"` | `.font-monospace` class |
| `routers/slack_api.py:338,340` | inline `sans-serif` and `monospace` in a raw HTML page | acceptable for a one-off credential page, but note it |
| `widgets/workflow_search.py:272` | `font-family: "Font Awesome 7 Pro"` for a `::before` glyph | `var(--fa-font-regular)` or an `<i>` element so the kit owns the family |

The BulkProgressCard card is rendered from `gooey_gui/types/bulk_progress_props.py` and
appears in the Copilot v2 shell. Its comment block in `app.css:511-514` acknowledges it
"deliberately keeps its own copy" of the status colours; the same is true of its fonts, and
nothing tracks when that debt gets paid.

### 4.2 Ghost fallbacks

`"Space Grotesk"` appears in the fallback chain at `custom.css:16`, `custom.css:190` and
five BulkProgressCard rules, but its `@import` is commented out at `custom.css:1`. A user
with Space Grotesk installed locally will see it; everyone else skips it. The same is true of
`avenir-lt-w01_85-heavy1475544`. Fallback chains should only name faces the page loads or
generic families.

The heading token `--gooey-font-heading: "Domine", basiercircle, Georgia, serif` puts a sans
before the serif fallback, so a blocked Domine degrades to a sans-serif heading, not a serif
one. The comment says this is intended, but it means the display headings and the UI face
collapse into the same look under a font block.

## 5. Weight drift

Avenir 85 Heavy is one weight. basiercircle has two files mapped to 400 and 700. Inter is
variable across 100-900. Rules written for the first two do not survive the switch:

- `custom.css:192-252` sets `font-weight: 400` on every heading level. On Avenir that reads
  heavy. Inside `.gooey-ds-page` and `.v2-app-shell`, the family flips to Inter but the
  weight stays 400, so headings render **Inter Regular**. Affected today:
  `HomePage/index.tsx:28` (`<h1 class="mb-5">`), `:33,:53` (`h4`),
  `HomePage/workflows.tsx:335`, `HistoryPage.tsx:51`, `WorkspaceHeader.tsx:16`,
  `WorkspaceMemoryTable.tsx:107`. Components that noticed compensate locally:
  `ToolPage.tsx:115` adds `fw-bold`, `RecipeTopBar.css:73` sets 600, `RecipeAbout.css:246`
  sets 500.
- `BulkProgressCard.css:236` sets `.bulk-progress-current strong { font-weight: 400 }`. That
  only looks bold because the family is Avenir. Converting the family without changing the
  weight will make the emphasised text disappear.
- `HomePage.css:313-320` documents the opposite problem: `.bold` (700) at Inter's true 700
  "read heavier than the card wanted", so `.workflow-card-title` was dropped to 500. There is
  no shared answer for what "card title weight" is.
- Weights in use across the v2 CSS: 400, 500, 600, 700, `bold`, `normal`. No token names
  them. `fw-bold` appears 6 times and `fw-normal` twice in Python; `.fw-medium` does not exist
  in Bootstrap 5.2.3.

## 6. Size, line-height and tracking drift

### 6.1 No scale, mixed units

The same visual size is written several ways:

| Intent | Spellings found |
|--------|-----------------|
| body-small (14px) | `14px` (NavigationSidebar.css:131,140,190; RecipeWorkspace.css:89; RecipeTopBar.css:162; AskGooeyNew.css:150,199), `0.875rem` (RecipeAbout.css:131,204,245; RecipeTopBar.css:235,305,344,362; RecipeWorkspace.css:238,382,519), `0.9rem` (BulkProgressCard, base.py, workflow_search.py, saved_workflow.py, chat_explore.py), `0.9em`, `smaller` |
| caption (12-13px) | `12px`, `13px`, `0.75rem`, `0.8rem`, `0.8125rem`, `0.82rem`, `0.85rem` |
| line-height | `1`, `1.15`, `1.2`, `1.25`, `1.3`, `1.35`, `1.5`, `1.6`, `120%`, `16px`, `20px`, `24px`, `35px`, `40px`, `44px` |

`RecipeWorkspace.css:89-91` and `:533,:536` need `!important` to win against react-select
and the JSON viewer. `custom.css:994` needs `!important` to force inputs to 16px on mobile
Safari because "most of the app renders its inputs inside 0.9rem wrappers".

The design tokens block at `app.css:436-483` defines colour, space and radius but no
`--gooey-text-*`, `--gooey-leading-*` or `--gooey-weight-*`. That is the gap every component
is filling by hand.

### 6.2 Python inline sizing

46 sites in Python set font size or weight inline. Grouped:

- `fontSize: "smaller"` (a relative keyword, compounds when nested):
  `daras_ai_v2/base.py:607,651,1927`, `widgets/history_filer.py:25,41`,
  `daras_ai_v2/text_to_speech_settings_widgets.py:451`, `base.py:2864` (`NAV_TABS_CSS`).
- `gui.styled` blocks carrying sizes: `recipes/VideoBots_v2.py:62,70`,
  `widgets/saved_workflow.py:53,175`, `widgets/workflow_search.py:267,278`,
  `daras_ai_v2/chat_explore.py:45`, `daras_ai_v2/analysis_results.py:48`,
  `widgets/base_header.py:22`.
- `style={"fontSize": ...}` dicts: `widgets/workflow_search.py:136`, `widgets/explore.py:178`,
  `base.py:2454`, TTS widgets `:675,677,680`, `bot_integration_widgets.py:51,63`,
  `doc_search_settings_widgets.py:68`.
- `fontWeight` dicts: `widgets/explore.py:122,131`, `history_filer.py:26,42`, `base.py:607,652`.
- Inline `fontSize` on Font Awesome `<i>` tags: `recipes/VideoBots.py:718,728,736`,
  `recipes/VideoGenPage.py:223`.

The `VideoBots_v2.py:55-71` comment is a good example of the cost: three paragraphs
explaining why a select and a button needed matching to "the pane strip's pills (14px)",
which a `--gooey-text-sm` token would have made a one-liner.

### 6.3 Letter-spacing and uppercase labels

Commit `ea4e4aab6` removed `letter-spacing: 1px` from `h3, h5` and `-0.02em` from the
Ask Gooey title. Remaining:

- `custom.css:626` `.cust-input-label { letter-spacing: 1px }` still on Avenir sizing.
- `RecipeAbout.css:243` `letter-spacing: normal` now undoes nothing. Its comment at `:239-240`
  describes the removed `h3` rule. Dead code.
- Uppercase eyebrow labels use four treatments: `RecipeTopBar.css:426-429` and `:780-783`
  (0.75rem / 600 / 0.04em), `BulkProgressCard.css:356-360` (0.8rem / 0.06em),
  `BulkProgressCard.css:430-434` (0.85rem / 0), and `IndustryBrowser.tsx:8`,
  `NewsFeed.tsx:6` (Bootstrap `h6 .small .text-uppercase`, no tracking, Avenir-weight
  heading rule). One `--gooey-tracking-caps` and one `.gooey-eyebrow` class would replace all
  four.

## 7. Recommendations

Ordered by risk. The first block can ship in one PR with no visual review outside the
affected surfaces.

### 7.1 Immediate, low risk

1. **Extend the v2 override list** at `app.css:497-500` with `.table > thead > tr > th` and
   `.streamlit-like-btn` so tables and copy buttons inside the shell stop rendering Avenir.
2. **Replace the five Avenir declarations in `BulkProgressCard.css`** with
   `font-family: var(--gooey-font-ui)` and give each a weight (600 for headline and stat
   value, 600 for the `strong`, 500 for the labels). Replace `:339` with the new mono token.
3. **Add `--gooey-font-mono`** to the token block, using Bootstrap's `--bs-font-monospace`
   value so `code`, `pre`, `.font-monospace`, `CodeEditor.tsx:167` and the two Python
   `fontFamily="monospace"` sites agree. Prefer the `.font-monospace` class in Python.
4. **`AskGooeyNew.css:154`** to `var(--gooey-font-ui)`.
5. **Delete `custom.css:3`** (the `.woff2` `@import`) and remove `"Space Grotesk"` and
   `avenir-lt-w01_85-heavy1475544` from every fallback chain.
6. **Delete the dead undo** at `RecipeAbout.css:239-243`.
7. **Add `.v2-topbar-container` to the Inter scope** at `app.css:485-491`, or render the top
   bar inside the `v2-app-shell` div in `base_v2.py`, so the recipe title stops computing to
   basiercircle.

### 7.2 Add a type scale before the next v2 recipe

Add to the `:root` block in `app.css`, next to the space and radius tokens:

```css
--gooey-text-xs: 0.75rem;    /* 12 - meta labels, eyebrows */
--gooey-text-sm: 0.8125rem;  /* 13 - captions, debug, tooltips */
--gooey-text-md: 0.875rem;   /* 14 - controls, pills, card body */
--gooey-text-base: 1rem;     /* 16 - body */
--gooey-text-lg: 1.25rem;    /* 20 */
--gooey-text-xl: 1.5rem;     /* 24 - h4 */
--gooey-text-2xl: 2rem;      /* 32 - h1-h3 */

--gooey-leading-none: 1;
--gooey-leading-tight: 1.2;
--gooey-leading-normal: 1.5;

--gooey-weight-regular: 400;
--gooey-weight-medium: 500;
--gooey-weight-semibold: 600;
--gooey-weight-bold: 700;

--gooey-tracking-caps: 0.04em;
```

Then convert the v2 component CSS files to the tokens, in this order, since each is
self-contained: `RecipeTopBar.css`, `RecipeWorkspace.css`, `RecipeAbout.css`,
`NavigationSidebar.css`, `HomePage.css`, `BulkProgressCard.css`, `AskGooeyNew.css`,
`RunDebugInfo.css`, `InsufficientCredits.css`. Replace px sizes with rem tokens; drop
`!important` where the token makes the specificity fight unnecessary.

### 7.3 Give the DS scope a heading weight

Add one rule under the family override at `app.css:500`:

```css
:is(.v2-app-shell, .gooey-ds-page, .ask-gooey-page) :is(h1, h2, h3, h4, h5, h6) {
  font-weight: var(--gooey-weight-semibold);
}
```

Then remove the per-component compensations (`ToolPage.tsx:115` `fw-bold`,
`RecipeTopBar.css:73`, `RecipeAbout.css:246`) or leave the ones that intentionally differ.
Confirm the intended heading weight against the Figma file first; 600 is a guess that
matches what RecipeTopBar already chose.

### 7.4 Make Inter the default, not the exception

Once every recipe on `all_pages_v2.py` is converted, or as its own decision earlier:

- Move `font-family: var(--gooey-font-ui)` onto `body` in `custom.css:141` and delete the
  four-marker rule. Delete the Avenir `@font-face`, its Wix CDN import and the
  `h1..h6, strong` Avenir rule. Keep basiercircle only as the token's fallback, or drop it.
- Delete `app.css:241` (`.gui-md-container strong`).
- This also fixes the v1 rail-versus-content mismatch on every page in one change.

### 7.5 Loading

- Add `<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>` and a
  `preload` for the latin Inter file to `root.tsx` links.
- Add Cyrillic, Greek, Vietnamese subsets for Inter (Google serves them under the same
  family) and decide on a fallback for Devanagari, Arabic and CJK, which Inter does not
  cover. Today those scripts render in basiercircle or the platform default with no
  policy.
- Consider self-hosting Inter and Domine next to the basiercircle files so the site has no
  runtime font dependency on gstatic or Wix.

### 7.6 Keep it from drifting again

- **Stylelint** in `gooey-gui/` with `declaration-property-value-disallowed-list` for
  `font-family` (allow only `var(--gooey-font-*)`, `inherit`, and the token file itself) and
  `declaration-no-important` scoped to font properties.
- **A pytest** that greps the Python tree for `fontFamily`, `fontSize`, `fontWeight` and
  `letterSpacing` in `style=` dicts and fails on new occurrences beyond a fixed allowlist,
  the same shape as the existing layout tests in `tests/test_layout_v2.py`.
- **Document the markers** in `gooey-gui/README.md`: which class a Python page adds to opt
  into the design system, and that inline font properties are not allowed.

## 8. Appendix: raw counts

| Measure | Count |
|---------|-------|
| CSS files with typography rules | 12 of 13 |
| `font-family` declarations outside the token block | 22 |
| Hardcoded Avenir declarations | 8 (custom.css 3, BulkProgressCard 5) |
| Distinct monospace stacks | 3 |
| Python inline `fontSize`/`fontWeight`/`fontFamily` sites | 46 across 18 files |
| Python uses of Bootstrap `.small` | 32 |
| `!important` on font-size | 5 |
| Distinct `line-height` values | 15 |
| Recipes on layout v2 | 1 (`VideoBotsPageV2`) |

Regenerate the inventory with:

```bash
grep -rnI --exclude-dir=node_modules --exclude-dir=.git --exclude-dir=build --exclude-dir=.claude --exclude-dir=public -iE "font-family|fontFamily" gooey-gui/app daras_ai_v2 widgets recipes routers gooey_gui templates
```

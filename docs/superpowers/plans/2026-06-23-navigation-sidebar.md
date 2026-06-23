# NavigationSidebar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the top-header chrome with a left navigation rail ("NavigationSidebar"), built on the HomePage React-component pattern, rolled out to every page that uses `page_wrapper`.

**Architecture:** A new React `NavigationSidebar` component is fed by a typed pydantic props model (`NavigationSidebarProps`) exactly like `HomePage`. A new `side_bar_page_wrapper` (sibling to `page_wrapper`) loads the data — reusing existing `widgets/home.py` loaders and workspace models — and mounts the component via `gui.model_component(...)`, flipping the page layout to horizontal `[rail][content+footer]`. Interactive server-stateful surfaces are wired natively in React via real routes/links: search → Explore page, workspace switch → a thin route reusing `set_current_workspace`, Gooey Builder → the existing `builder-sidebar:open` event (the Builder sidebar itself is untouched).

**Tech Stack:** Python 3.10 / pydantic / FastAPI + `gooey_gui`; React 17 + TypeScript; Bootstrap 5 utilities; FontAwesome Pro kit (already loaded globally).

## Global Constraints

*Every task's requirements implicitly include this section. Copy exact values verbatim.*

- **Component pattern (follow HomePage exactly):** pydantic model in `gooey_gui/types/<name>_props.py` carrying `_component: str = "<Name>"` → run `python scripts/generate_gui_types.py` to regenerate the sibling `.d.ts` → the `.tsx` imports `import type { X } from "@gooey-types/<name>_props"` and is re-exported from `gooey-gui/app/components/index.ts` → Python renders via `gui.model_component(model)`.
- **NEVER hand-edit a generated `.d.ts`** (banner says "Do not edit manually"). Change the pydantic model and re-run `python scripts/generate_gui_types.py`.
- **Pydantic fields:** the generator marks every field required-but-nullable. Use `| None` (default `None`) or `= []`/`= ""` for values a builder may omit. Mirror the style in `gooey_gui/types/home_page_props.py`.
- **React styling = Bootstrap 5 utility classes** (codebase convention). Do NOT introduce `--gy-*` color variables; map the prototype's colors to Bootstrap semantic classes (`text-body`, `text-muted`, `bg-body`, `bg-body-secondary`, `border`, `rounded`, `btn`, etc.). Only `NavigationSidebar.css` carries what utilities can't express: rail width + width transition, the custom thin rail scrollbar, the off-canvas drawer/overlay, and the Saved tree line.
- **Colors are explicitly out of scope** — do not port `colors_and_type.css` or define gy tokens. Approximate with Bootstrap semantics.
- **FontAwesome:** the FA **Pro** kit (`kit.fontawesome.com/8af9787bd5.js`) is loaded globally in `gooey-gui/app/root.tsx`; the prototype's `fa-regular`/`fa-solid` classes render as-is. Use them directly.
- **Exact values:** New button → `/explore2/`. Search rail item → the Explore page path (`get_route_path(explore_page)`). Mobile drawer breakpoint = Bootstrap `lg` (992px). Recents shown in the rail = **10** max. Gooey Builder button renders **only** when `can_launch_gooey_builder(request, workspace)` is true.
- **Reuse, do not reimplement:** recents/saved via `widgets.home._load_recent_workflows` / `_load_saved_workflows`; saved "View all" via `widgets.home._saved_workflows_href`; workspaces via `user.cached_workspaces`; workspace switch via `workspaces.widgets.set_current_workspace`; anonymous sign-in is a plain link to `/login/` (do NOT embed Google One Tap markup in React).
- **Do NOT touch the Builder sidebar** (`widgets/sidebar.py` `sidebar_layout`, `daras_ai_v2/gooey_builder.py`). The rail only fires `window.dispatchEvent(new CustomEvent("builder-sidebar:open"))`.
- **Collapse persistence** uses the same session mechanism as `widgets/sidebar.py` `sidebar_layout` (a `<key>:default-open`-style key copied between `gui.session_state` and `session`) plus the React `state`/`onChange` persistence pattern from `gooey-gui/app/components/Sidebar.tsx`.
- **Do NOT modify `page_wrapper`** until its callers are migrated. Build `side_bar_page_wrapper` alongside it; it accepts the SAME parameters as `page_wrapper`: `request, className="", search_filters=None, show_search_bar=True, page=None`, and is a context-manager generator yielding `current_workspace` just like `page_wrapper`.
- **Testing reality:** there is no React component test harness — UI tasks verify via `cd gooey-gui && npm run typecheck` plus running the app and manual checks. Python logic (the switch route, the props builder) gets `pytest` tests following the repo's existing test style.
- **Commits:** conventional messages (`feat:`, `refactor:`, …) matching repo style; commit at each step boundary.
- **Reference:** the design prototype is saved at `docs/superpowers/plans/reference/side-nav-stopgap.jsx` — it is the visual/interaction source of truth and lists the port rules and exact section order/widths.

---

### Task 1: Type contract + foundation rail on Home

**Files:**
- Create: `gooey_gui/types/navigation_sidebar_props.py`
- Generate: `gooey_gui/types/navigation_sidebar_props.d.ts` (via script — do not hand-write)
- Create: `gooey-gui/app/components/NavigationSidebar/index.tsx`
- Create: `gooey-gui/app/components/NavigationSidebar/NavigationSidebar.css`
- Modify: `gooey-gui/app/components/index.ts` (add `export * from "./NavigationSidebar";`)
- Create: `widgets/navigation_sidebar.py`
- Modify: `routers/root.py` (add `side_bar_page_wrapper`; switch `home_page` to use it)

**Interfaces:**
- Produces — the COMPLETE typed contract that all later tasks consume and populate. Define every model now; later tasks populate the currently-empty fields and render them:

```python
# gooey_gui/types/navigation_sidebar_props.py
from __future__ import annotations
import pydantic


class NavItemData(pydantic.BaseModel):
    key: str
    label: str
    icon: str          # FontAwesome class, e.g. "fa-regular fa-house"
    href: str


class NavWorkflowData(pydantic.BaseModel):
    title: str
    href: str
    image_url: str | None = None
    icon: str | None = None        # FA class fallback when no image


class WorkspaceData(pydantic.BaseModel):
    id: int
    name: str
    icon_html: str                 # workspace.html_icon()
    is_current: bool = False


class MenuLinkData(pydantic.BaseModel):
    label: str
    href: str
    icon: str | None = None        # FA class


class NavUserData(pydantic.BaseModel):
    name: str
    initial: str
    photo_url: str | None = None


class GooeyBuilderData(pydantic.BaseModel):
    photo_url: str


class NavigationSidebarProps(pydantic.BaseModel):
    _component: str = "NavigationSidebar"

    # primary nav (Task 1)
    logo_image_url: str
    nav_items: list[NavItemData] = []
    active_key: str | None = None
    new_href: str
    search_href: str

    # workflow lists (Task 3)
    saved_href: str = ""
    saved_workflows: list[NavWorkflowData] = []
    recent_workflows: list[NavWorkflowData] = []

    # identity / workspace / menu (Task 4) + anonymous (Task 5)
    user: NavUserData | None = None              # None => anonymous
    current_workspace: WorkspaceData | None = None
    workspaces: list[WorkspaceData] = []
    menu_links: list[MenuLinkData] = []
    logout_href: str = ""
    switch_workspace_href: str = ""              # POST/GET target, {workspace_id} templated by React
    login_href: str = "/login/"

    # gooey builder (Task 7)
    gooey_builder: GooeyBuilderData | None = None

    # collapse (Task 2)
    default_collapsed: bool = False
```

- Produces — `widgets/navigation_sidebar.py::build_props(request) -> NavigationSidebarProps`. In Task 1 it populates only `logo_image_url`, `nav_items` (New is separate via `new_href`), `active_key`, `new_href`, `search_href`. Later tasks extend this same function.
- Produces — `routers/root.py::side_bar_page_wrapper(request, className="", search_filters=None, show_search_bar=True, page=None)` context-manager generator: builds props, mounts `gui.model_component(build_props(request))`, lays out `[rail][content]`, yields `current_workspace`, renders footer. Keeps `gtag.html`, `footer.html`, `login_scripts.html`, and the Builder sidebar mount intact (copy from `page_wrapper`).
- Produces — React `export function NavigationSidebar(props: CustomComponentProps & NavigationSidebarProps)` exported from `components/index.ts` under the name `NavigationSidebar`.

- [ ] **Step 1: Define the pydantic model.** Create `gooey_gui/types/navigation_sidebar_props.py` with the code in the Interfaces block above.

- [ ] **Step 2: Generate the TypeScript types.**

Run: `python scripts/generate_gui_types.py`
Expected: prints `gooey_gui.types.navigation_sidebar_props (N models) -> gooey_gui/types/navigation_sidebar_props.d.ts`; the `.d.ts` exists with a "Do not edit manually" banner and a `NavigationSidebarProps` type.

- [ ] **Step 3: Build the React foundation component.** Create `gooey-gui/app/components/NavigationSidebar/index.tsx`. Follow `gooey-gui/app/components/HomePage/index.tsx` for conventions (import the css, `import type { NavigationSidebarProps } from "@gooey-types/navigation_sidebar_props"`, `import type { CustomComponentProps } from "~/components"`). Render the rail structure from `docs/superpowers/plans/reference/side-nav-stopgap.jsx` but for Task 1 only the header (logo `<img src={logo_image_url}/>` + inline `GooeyBot` glyph), the sticky **New** item (`href={new_href}`), and the primary nav items (`nav_items.map`, each an `<a href>` with its `icon`, bold + `bg-body-secondary` when `key === active_key`), plus a **Search** item (`href={search_href}`). Fixed 264px width via the css class. Use Bootstrap utilities for layout (`d-flex flex-column`, `gap-*`, `p-*`, `rounded`, `text-body`/`text-muted`). Stub later sections as empty/hidden — they arrive in later tasks.

- [ ] **Step 4: Register the component.** In `gooey-gui/app/components/index.ts` add `export * from "./NavigationSidebar";`.

- [ ] **Step 5: Create the css.** `NavigationSidebar.css`: `.nav-sidebar { width: 264px; flex: none; height: 100vh; ... transition: width 200ms ease; }` and the thin rail scrollbar rules from the prototype. No color tokens.

- [ ] **Step 6: Build the props builder.** Create `widgets/navigation_sidebar.py` with `build_props(request)` populating the Task-1 fields. Use `daras_ai_v2.settings.GOOEY_LOGO_IMG` for `logo_image_url`; `get_route_path` for hrefs: Home→`home_page`, Explore→`explore_page` (also `search_href`), Saved→`saved_route`; `new_href="/explore2/"`. Derive `active_key` from `request.url.path`.

- [ ] **Step 7: Add `side_bar_page_wrapper`.** In `routers/root.py`, add the generator (copy `page_wrapper`'s body, remove the top-header navbar block, mount the rail to the left of a `d-flex` row, keep gtag/footer/login-scripts and the Builder sidebar mount). Then change `home_page` (root.py:234) to use `side_bar_page_wrapper`.

- [ ] **Step 8: Verify.**
Run: `python scripts/generate_gui_types.py` (clean), then `cd gooey-gui && npm run typecheck`
Expected: typecheck passes. Run the app, open Home: a left rail shows the logo, New, Home/Explore/Saved/Search links that navigate; Home is highlighted active; top header is gone on Home only.

- [ ] **Step 9: Commit.**
```bash
git add gooey_gui/types/navigation_sidebar_props.py gooey_gui/types/navigation_sidebar_props.d.ts gooey-gui/app/components/NavigationSidebar/ gooey-gui/app/components/index.ts widgets/navigation_sidebar.py routers/root.py
git commit -m "feat: NavigationSidebar foundation rail on home"
```

---

### Task 2: Collapse / expand with session persistence

**Files:**
- Modify: `gooey-gui/app/components/NavigationSidebar/index.tsx`
- Modify: `gooey-gui/app/components/NavigationSidebar/NavigationSidebar.css`
- Modify: `routers/root.py` (`side_bar_page_wrapper`)
- Modify: `widgets/navigation_sidebar.py` (`build_props`)

**Interfaces:**
- Consumes: `NavigationSidebarProps.default_collapsed: bool` (already defined in Task 1).
- Produces: a stable session key `"nav-sidebar:default-collapsed"` used by both `side_bar_page_wrapper` and the React component.

- [ ] **Step 1: Persist on the server side.** In `side_bar_page_wrapper`, mirror `widgets/sidebar.py::sidebar_layout`: read `gui.session_state["nav-sidebar:default-collapsed"]` (fallback to `session.get(...)`), copy into `session`, and pass the value into `build_props` so `default_collapsed` is set.

- [ ] **Step 2: Collapse state in React.** In `index.tsx`, `const [collapsed, setCollapsed] = useState(props.default_collapsed)`. Add a `useEffect` mirroring `Sidebar.tsx`: when `collapsed` changes, set `state["nav-sidebar:default-collapsed"] = collapsed` and call `onChange()`.

- [ ] **Step 3: Render collapsed/expanded.** Width 264↔66 via a css class toggle. Collapsed: center icons, hide labels/wordmark, hide Saved-tree/Recent list (Recent becomes a single `fa-clock-rotate-left` item), show a dark hover tooltip to the right of each item (from the prototype's `RailTooltip`). Header gets a collapse button (`fa-regular fa-sidebar`); collapsed rail expands on click of empty rail area.

- [ ] **Step 4: Verify.**
Run: `cd gooey-gui && npm run typecheck`
Expected: passes. In the app: collapse the rail, reload — it stays collapsed; expand, reload — stays expanded. Collapsed items show tooltips.

- [ ] **Step 5: Commit.** `git commit -m "feat: NavigationSidebar collapse with session persistence"`

---

### Task 3: Recent + Saved workflow lists

**Files:**
- Create: `gooey-gui/app/components/NavigationSidebar/WorkflowList.tsx`
- Modify: `gooey-gui/app/components/NavigationSidebar/index.tsx`
- Modify: `widgets/navigation_sidebar.py`

**Interfaces:**
- Consumes: `saved_workflows`, `recent_workflows` (`list[NavWorkflowData]`), `saved_href`.
- Produces: `export function WorkflowList(...)` rendering a list of `NavWorkflowData` rows (rounded image with `object-fit: cover`, or FA `icon` fallback, then an ellipsised label `<a href>`), with an `indented` variant for the Saved tree.

- [ ] **Step 1: Populate the builder.** In `widgets/navigation_sidebar.py`, reuse `widgets.home._load_saved_workflows(user, workspace)` and `_load_recent_workflows(user, workspace)`; map each `WorkflowCardData` → `NavWorkflowData(title=card.title, href=card.href, image_url=<preview image if any>, icon=card.workflow_icon)`. Recents capped at 10 (slice the list). `saved_href = widgets.home._saved_workflows_href(workspace)`. Get `user`/`workspace` the same way `widgets/home.py::render` does (`get_current_workspace`).

- [ ] **Step 2: Build `WorkflowList.tsx`** per the Interfaces block + the prototype's `RecentRow`. Image-with-icon-fallback; ellipsis on overflow; `indent` prop for the tree variant.

- [ ] **Step 3: Render in the rail.** In `index.tsx`: make **Saved** expandable into an indented `WorkflowList` (saved_workflows) with the 1px tree line + a "View all" link to `saved_href`; add a collapsible **Recent** section (label + chevron-on-hover) rendering `WorkflowList` of `recent_workflows`. Hidden when collapsed (per Task 2 rules).

- [ ] **Step 4: Verify.** `cd gooey-gui && npm run typecheck`; in the app, Home rail shows real recent + saved workflows with images, links navigate, Saved tree expands/collapses, "View all" works.

- [ ] **Step 5: Commit.** `git commit -m "feat: NavigationSidebar recent and saved workflow lists"`

---

### Task 4: Identity footer + user menu + workspace switch

**Files:**
- Create: `gooey-gui/app/components/NavigationSidebar/IdentityMenu.tsx`
- Modify: `gooey-gui/app/components/NavigationSidebar/index.tsx`
- Modify: `widgets/navigation_sidebar.py`
- Modify: `routers/workspace.py` (new switch route)
- Create/Modify test: `workspaces/` test module for the switch route (follow the repo's existing route-test style)

**Interfaces:**
- Consumes: `user`, `current_workspace`, `workspaces`, `menu_links`, `logout_href`, `switch_workspace_href`.
- Produces: a switch route at a path like `/workspaces/switch/{workspace_id}/` that calls `set_current_workspace(request.session, workspace_id)` and redirects to `?next=` (or referer/home). `build_props` sets `switch_workspace_href` to that path with a `{workspace_id}` placeholder the React side substitutes (or React posts the id).
- Produces: `export function IdentityMenu(...)` — footer identity button + popover (workspace selector submenu + menu rows + logout).

- [ ] **Step 1: Add the switch route.** In `routers/workspace.py`, add a route (mirror the existing `@gui.route`/FastAPI route style already in that file) that takes `workspace_id`, calls `set_current_workspace(session, workspace_id)`, and raises `gui.RedirectException(next or get_route_path(home_page))`. Validate the user is a member before switching.

- [ ] **Step 2: Test the switch route.** Write a `pytest` test (matching repo test conventions) asserting that hitting the route sets `session[SESSION_SELECTED_WORKSPACE]` to the target id and redirects; and that switching to a workspace the user does not belong to is rejected. Run it, confirm it fails first (route absent), then passes.

- [ ] **Step 3: Populate the builder.** In `build_props`: set `user` (name=`user.display_name`/`first_name`, `initial`=first letter, `photo_url`); build `current_workspace` + `workspaces` from `user.cached_workspaces` (`WorkspaceData(id, name=ws.display_name(user), icon_html=ws.html_icon(), is_current=ws.id==current.id)`); `menu_links` from the account route paths (profile/billing/plans/members) + `settings.HEADER_LINKS` (Docs/API/etc.); `logout_href` from the logout route; `switch_workspace_href` = the route path.

- [ ] **Step 4: Build `IdentityMenu.tsx`** per the prototype's `IdentityFooter`/`UserMenu`/`WorkspaceList`. Workspace rows POST/navigate to `switch_workspace_href` for the given id; menu rows are `<a href>`; Log out → `logout_href`.

- [ ] **Step 5: Render the footer** in `index.tsx` (logged-in path only; anonymous is Task 5).

- [ ] **Step 6: Verify.** Run the new pytest test (passes); `cd gooey-gui && npm run typecheck`; in the app: footer shows identity, menu opens, menu links navigate, switching a workspace reloads into it.

- [ ] **Step 7: Commit.** `git commit -m "feat: NavigationSidebar identity menu and workspace switch"`

---

### Task 5: Anonymous (logged-out) reduced rail

**Files:**
- Modify: `gooey-gui/app/components/NavigationSidebar/index.tsx`
- Modify: `gooey-gui/app/components/NavigationSidebar/IdentityMenu.tsx`
- Modify: `widgets/navigation_sidebar.py`

**Interfaces:**
- Consumes: `user is None` (anonymous), `login_href`.

- [ ] **Step 1: Builder anonymous path.** In `build_props`, when `request.user` is None/anonymous: leave `user`/`current_workspace`/`workspaces`/recents/saved empty; keep `logo`, Explore, and the public `HEADER_LINKS`; set `login_href="/login/"` (with a `next` param to the current url, matching `anonymous_login_container`).

- [ ] **Step 2: Render reduced rail.** In `index.tsx`/`IdentityMenu.tsx`: when `user` is null, hide New/Home/Saved/Recent/identity; show logo + Explore + public links; footer becomes a **Sign In** row linking to `login_href`.

- [ ] **Step 3: Verify.** `cd gooey-gui && npm run typecheck`; logged out, open Explore/login: reduced rail with Sign In → `/login/`.

- [ ] **Step 4: Commit.** `git commit -m "feat: NavigationSidebar anonymous reduced rail"`

---

### Task 6: Mobile off-canvas drawer

**Files:**
- Modify: `gooey-gui/app/components/NavigationSidebar/index.tsx`
- Modify: `gooey-gui/app/components/NavigationSidebar/NavigationSidebar.css`

**Interfaces:**
- Consumes: nothing new.

- [ ] **Step 1: Responsive css.** Below `lg` (992px): hide the rail by default; add an overlay + slide-in transform for an "open" state; the rail renders over content with a scrim.

- [ ] **Step 2: Mobile top bar + toggle.** In `index.tsx`, render a slim top bar (hamburger + logo) on `<lg`; hamburger toggles a `drawerOpen` state; tapping the scrim or a nav link closes it. Use `d-lg-none` / `d-none d-lg-flex` Bootstrap helpers.

- [ ] **Step 3: Verify.** `cd gooey-gui && npm run typecheck`; at narrow width the rail is hidden, hamburger opens the drawer over content, links work and close it; at ≥992px the rail is normal.

- [ ] **Step 4: Commit.** `git commit -m "feat: NavigationSidebar mobile off-canvas drawer"`

---

### Task 7: Gooey Builder button on recipe pages

**Files:**
- Modify: `gooey-gui/app/components/NavigationSidebar/index.tsx`
- Modify: `widgets/navigation_sidebar.py`
- Modify: `routers/root.py` (migrate recipe run/preview wrappers to `side_bar_page_wrapper`)

**Interfaces:**
- Consumes: `gooey_builder: GooeyBuilderData | None`.

- [ ] **Step 1: Populate when available.** In `build_props`, if `can_launch_gooey_builder(request, workspace)` and the builder integration exists, set `gooey_builder=GooeyBuilderData(photo_url=<branding photo, same source as render_gooey_builder_launcher>)`; else `None`.

- [ ] **Step 2: Render the button.** In `index.tsx`, when `gooey_builder` is set, render the Builder button (img = `gooey_builder.photo_url`) above the footer; `onClick={() => window.dispatchEvent(new CustomEvent("builder-sidebar:open"))}`. Do NOT render the old fixed launcher in `side_bar_page_wrapper` (the rail button replaces it); keep `render_gooey_builder` (the sidebar contents) mounted unchanged.

- [ ] **Step 3: Migrate recipe run/preview.** Point the recipe run/preview `page_wrapper(request, page=page)` call(s) (root.py:711 path) at `side_bar_page_wrapper`, keeping the `page=` argument so the Builder sidebar still mounts.

- [ ] **Step 4: Verify.** `cd gooey-gui && npm run typecheck`; open a recipe run page: rail shows the Builder button, clicking it opens the existing Builder sidebar; the button is absent on Home/Explore.

- [ ] **Step 5: Commit.** `git commit -m "feat: NavigationSidebar gooey builder button on recipe pages"`

---

### Task 8: Global rollout + retire `page_wrapper`

**Files:**
- Modify: `routers/root.py`, `routers/account.py`, `routers/local_auth.py` (and any other `page_wrapper` callers)
- Remove: `page_wrapper` from `routers/root.py` once unused

**Interfaces:**
- Consumes: everything from Tasks 1–7.

- [ ] **Step 1: Inventory callers.** `grep -rn "page_wrapper(" --include=*.py .` (excluding the def and `side_bar_page_wrapper`). Confirm the full list: root (explore, account, recipe tabs not yet migrated, others), `account.py::account_page_wrapper`, `local_auth.py` (login pages).

- [ ] **Step 2: Migrate each caller** to `side_bar_page_wrapper`, preserving each call's arguments (`search_filters`, `show_search_bar`, `page`). On Explore, confirm the removed header search is acceptable (search is now the rail's Explore link); on account tabs, confirm the rail + account tabs coexist; login pages use the anonymous rail.

- [ ] **Step 3: Remove `page_wrapper`** once no callers remain (or keep only if a caller genuinely still needs the old chrome — flag to the human if so).

- [ ] **Step 4: Verify.** `cd gooey-gui && npm run typecheck`; manually sweep: Home, Explore, a recipe run page (Builder works), an account tab, the login page, each at desktop and <992px width. Collapse persists; workspace switch works; no page still shows the old top header.

- [ ] **Step 5: Commit.** `git commit -m "refactor: roll NavigationSidebar out to all page_wrapper pages"`

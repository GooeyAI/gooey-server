import type {
  PageShellConfig,
  SingleLayout,
  SplitLayout,
  SurfaceId,
  WorkspaceView,
} from "@gooey-types/recipe_workspace_props";

export type WorkspaceLayout = SingleLayout | SplitLayout;

export type WorkspaceState = {
  layout: WorkspaceLayout;
  handled_run_id: string | null;
};

export type PaneRole = "closed" | "solo" | "major" | "minor";
export type PaneRoles = Record<SurfaceId, PaneRole>;

export type WorkspaceControls = {
  addEditor: boolean;
  addPreview: boolean;
  closePreview: boolean;
};

/* The view a workspace opens on, derived from the url alone: the server sends
   `initial_layout` per url - About on a published run, the work view on a saved run - so
   the same url always opens the same way, for everyone. */
export function initialWorkspaceState(
  config: PageShellConfig,
  navigationState: unknown
): WorkspaceState {
  const carried = carriedLayoutFor(config);
  if (config.route_layout) {
    return {
      layout: config.route_layout,
      handled_run_id: config.active_run_id ?? null,
    };
  }

  const navigationLayout = workspaceLayoutFromNavigationState(navigationState);
  return revealRunLayout(
    {
      layout: navigationLayout ?? carried ?? config.initial_layout,
      handled_run_id: null,
    },
    config
  );
}

export function workspaceLayoutNavigationState(layout: WorkspaceLayout): {
  workspaceLayout: WorkspaceLayout;
} {
  return { workspaceLayout: layout };
}

export function workspaceLayoutFromNavigationState(
  state: unknown
): WorkspaceLayout | null {
  if (!state || typeof state !== "object") {
    return null;
  }
  const { workspaceLayout } = state as { workspaceLayout?: unknown };
  if (!isWorkspaceLayout(workspaceLayout)) {
    return null;
  }
  return workspaceLayout;
}

export function clearWorkspaceLayoutNavigationState() {
  const historyState = window.history.state;
  const userState = historyState?.usr;
  if (
    !userState ||
    typeof userState !== "object" ||
    !("workspaceLayout" in userState)
  ) {
    return;
  }
  const remainingUserState = {
    ...(userState as Record<string, unknown>),
  };
  delete remainingUserState.workspaceLayout;
  const nextUserState = Object.keys(remainingUserState).length
    ? remainingUserState
    : null;
  window.history.replaceState({ ...historyState, usr: nextUserState }, "");
}

/** Whether starting a run should swap this layout for the one that shows the output.
 *
 * Only from the editor on its own. That is the view a run would start out of sight from, so
 * it gives way to the split. Every other view was chosen to show something in particular -
 * About to read about the workflow, Preview to watch it - and a run is no reason to take it
 * away. Preview is already the output, and About keeps the preview beside it on a wide
 * screen, so nothing is hidden by staying put either.
 */
/** Move to the run layout when a run starts, from the views where that is wanted.
 *
 *  Deferred one macrotask. The timer does not *order* anything against the submit - it
 *  yields, and the submit has already been dispatched by the time it runs, because both
 *  happen off the same click. Written once because two run buttons need it and two copies
 *  of a timing assumption are two things to get wrong.
 */
export function revealRunOutput(
  layout: WorkspaceLayout,
  runLayout: WorkspaceLayout,
  selectLayout: (next: WorkspaceLayout) => void
) {
  const next = shouldRevealRunOutput(layout) ? runLayout : layout;
  // Running redirects to the run's own url, whose layout is the work view - so the view to
  // end on rides across that one navigation, or Preview and About are swapped out by it.
  carriedRunLayout = { layout: next, runId: null };
  if (next !== layout) {
    window.setTimeout(() => selectLayout(next), 0);
  }
}

/* Set when Run is pressed, and held until the run it produced is over or replaced. A
   module-level handoff because a server redirect carries no router state to put it in.

   Bound to a run id rather than read once: the workspace re-renders many times while a run
   is polled, and every one of those asks for the layout again. */
let carriedRunLayout: { layout: WorkspaceLayout; runId: string | null } | null =
  null;

/* Pure, so the first render can ask before the effect that binds it has run - that render
   is the one that would otherwise lay out the run url's own view and animate away from it. */
export function peekCarriedRunLayout(
  config: PageShellConfig
): WorkspaceLayout | null {
  if (!carriedRunLayout) return null;
  // still on the page Run was pressed from; the run's own url has not arrived yet
  const runId = config.active_run_id ?? null;
  if (!runId) return null;
  if (carriedRunLayout.runId === null) return carriedRunLayout.layout;
  return carriedRunLayout.runId === runId ? carriedRunLayout.layout : null;
}

function carriedLayoutFor(config: PageShellConfig): WorkspaceLayout | null {
  const layout = peekCarriedRunLayout(config);
  if (layout) {
    carriedRunLayout = { layout, runId: config.active_run_id ?? null };
  } else if (carriedRunLayout && carriedRunLayout.runId !== null) {
    carriedRunLayout = null;
  }
  return layout;
}

export function shouldRevealRunOutput(layout: WorkspaceLayout): boolean {
  return layout.kind === "single" && layout.surface === "editor";
}

export function revealRunLayout(
  state: WorkspaceState,
  config: PageShellConfig
): WorkspaceState {
  if (!config.active_run_id || config.active_run_id === state.handled_run_id) {
    return state;
  }
  return {
    // The run counts as handled either way, so a view the user picked for this run is not
    // swapped out later by the same run arriving again.
    layout: shouldRevealRunOutput(state.layout)
      ? config.run_layout
      : state.layout,
    handled_run_id: config.active_run_id,
  };
}

export function isRootLayout(
  shown: WorkspaceLayout,
  initial: WorkspaceLayout,
  narrowSurface: SurfaceId,
  isNarrow: boolean
): boolean {
  return layoutsEqual(
    shown,
    foldForNarrowViewport(initial, narrowSurface, isNarrow)
  );
}

export function foldForNarrowViewport(
  layout: WorkspaceLayout,
  narrowSurface: SurfaceId,
  isNarrow: boolean
): WorkspaceLayout {
  if (!isNarrow || layout.kind === "single") {
    return layout;
  }
  if (layout.primary === "about") {
    return singleLayout("about");
  }
  if (layoutHasSurface(layout, narrowSurface)) {
    return singleLayout(narrowSurface);
  }
  return singleLayout(layout.primary);
}

export function paneRolesForLayout(layout: WorkspaceLayout): PaneRoles {
  const roles: PaneRoles = {
    about: "closed",
    editor: "closed",
    preview: "closed",
  };
  if (layout.kind === "single") {
    roles[layout.surface] = "solo";
    return roles;
  }
  roles[layout.primary] = "major";
  roles[layout.secondary] = "minor";
  return roles;
}

export function viewForLayout(
  views: readonly WorkspaceView[],
  layout: WorkspaceLayout
): WorkspaceView | null {
  return views.find((view) => layoutsEqual(view.layout, layout)) ?? null;
}

export function activeViewForLayouts(
  views: readonly WorkspaceView[],
  shown: WorkspaceLayout,
  stored: WorkspaceLayout,
  workspaceActive: boolean
): WorkspaceView | null {
  if (!workspaceActive) {
    return null;
  }
  return viewForLayout(views, shown) ?? viewForLayout(views, stored);
}

export function collapsePane(
  layout: WorkspaceLayout,
  surface: SurfaceId
): WorkspaceLayout {
  if (layout.kind === "single" || !layoutHasSurface(layout, surface)) {
    return layout;
  }
  if (layout.primary === surface) {
    return singleLayout(layout.secondary);
  }
  return singleLayout(layout.primary);
}

export function workspaceControlsForLayout(
  layout: WorkspaceLayout
): WorkspaceControls {
  const noControls: WorkspaceControls = {
    addEditor: false,
    addPreview: false,
    closePreview: false,
  };
  if (layoutHasSurface(layout, "about")) {
    return noControls;
  }
  if (layout.kind === "split") {
    return {
      ...noControls,
      closePreview: layoutHasSurface(layout, "preview"),
    };
  }
  if (layout.surface === "editor") {
    return { ...noControls, addPreview: true };
  }
  if (layout.surface === "preview") {
    return { ...noControls, addEditor: true };
  }
  return noControls;
}

/** Where to navigate to reach the workspace, or null when we are already on it.
 *  Named for what it answers: there is no layout in the question. */
export function workspaceHrefToNavigate(
  workspaceActive: boolean,
  workspaceHref: string
): string | null {
  if (workspaceActive || !workspaceHref) {
    return null;
  }
  return appRelativeHref(workspaceHref);
}

export function singleLayout(surface: SurfaceId): SingleLayout {
  return { kind: "single", surface };
}

export function splitLayout(
  primary: SurfaceId,
  secondary: SurfaceId
): SplitLayout {
  if (primary === secondary) {
    throw new Error("A split layout requires two different surfaces");
  }
  return { kind: "split", primary, secondary };
}

export function layoutsEqual(
  left: WorkspaceLayout,
  right: WorkspaceLayout
): boolean {
  if (left.kind !== right.kind) {
    return false;
  }
  if (left.kind === "single" && right.kind === "single") {
    return left.surface === right.surface;
  }
  if (left.kind === "split" && right.kind === "split") {
    return left.primary === right.primary && left.secondary === right.secondary;
  }
  return false;
}

function isWorkspaceLayout(value: unknown): value is WorkspaceLayout {
  if (!value || typeof value !== "object") {
    return false;
  }
  const layout = value as Partial<WorkspaceLayout>;
  if (layout.kind === "single") {
    return isSurfaceId(layout.surface);
  }
  if (layout.kind !== "split") {
    return false;
  }
  return (
    isSurfaceId(layout.primary) &&
    isSurfaceId(layout.secondary) &&
    layout.primary !== layout.secondary
  );
}

function layoutHasSurface(
  layout: WorkspaceLayout,
  surface: SurfaceId
): boolean {
  if (layout.kind === "single") {
    return layout.surface === surface;
  }
  return layout.primary === surface || layout.secondary === surface;
}

function isSurfaceId(value: unknown): value is SurfaceId {
  return value === "about" || value === "editor" || value === "preview";
}

/** Python sends absolute app urls; Remix's `navigate` wants a path. Handed an absolute one
 *  it resolves it against the origin, which doubles it - `/http://host/agent/` - and 404s.
 *  Every navigation off a server-sent href has to come through here. */
export function appRelativeHref(href: string): string {
  if (!href.startsWith("http://") && !href.startsWith("https://")) {
    return href;
  }
  const url = new URL(href);
  return `${url.pathname}${url.search}${url.hash}`;
}

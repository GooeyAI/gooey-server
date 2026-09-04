import type {
  PageShellConfig,
  SingleLayout,
  SplitLayout,
  SurfaceId,
  WorkspaceView,
} from "@gooey-types/recipe_workspace_props";

export type WorkspaceLayout = SingleLayout | SplitLayout;

export type PersistedWorkspaceState = {
  version: 1;
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

export function initialWorkspaceState(
  config: PageShellConfig,
  storage: { getItem(key: string): string | null },
  navigationState: unknown
): PersistedWorkspaceState {
  const stored = storedWorkspaceState(storage, config);
  if (config.route_layout) {
    return {
      version: 1,
      layout: config.route_layout,
      handled_run_id: config.active_run_id ?? stored.handled_run_id,
    };
  }

  const navigationLayout = workspaceLayoutFromNavigationState(navigationState);
  const initial = navigationLayout
    ? { ...stored, layout: navigationLayout }
    : stored;
  return revealRunLayout(initial, config);
}

export function normalizeWorkspaceLayout(
  value: unknown,
  fallback: WorkspaceLayout
): WorkspaceLayout {
  if (isWorkspaceLayout(value)) {
    return value;
  }
  const migrated = migrateLegacyLayout(value);
  return migrated ?? fallback;
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
export function shouldRevealRunOutput(layout: WorkspaceLayout): boolean {
  return layout.kind === "single" && layout.surface === "editor";
}

export function revealRunLayout(
  state: PersistedWorkspaceState,
  config: PageShellConfig
): PersistedWorkspaceState {
  if (!config.active_run_id || config.active_run_id === state.handled_run_id) {
    return state;
  }
  return {
    version: 1,
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

export function workspaceTargetForLayout(
  workspaceActive: boolean,
  workspaceHref: string
): string | null {
  if (workspaceActive || !workspaceHref) {
    return null;
  }
  return appRelativeHref(workspaceHref);
}

export function paneVisibility(hydrated: boolean): "hidden" | "visible" {
  if (!hydrated) {
    return "hidden";
  }
  return "visible";
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

function storedWorkspaceState(
  storage: { getItem(key: string): string | null },
  config: PageShellConfig
): PersistedWorkspaceState {
  let stored: unknown = null;
  try {
    const serialized = storage.getItem(config.storage_key);
    if (serialized) {
      stored = JSON.parse(serialized);
    }
  } catch {
    return defaultWorkspaceState(config);
  }
  if (isPersistedWorkspaceState(stored)) {
    return {
      version: 1,
      layout: normalizeWorkspaceLayout(stored.layout, config.initial_layout),
      handled_run_id: stored.handled_run_id,
    };
  }
  return {
    version: 1,
    layout: normalizeWorkspaceLayout(stored, config.initial_layout),
    handled_run_id: null,
  };
}

function defaultWorkspaceState(
  config: PageShellConfig
): PersistedWorkspaceState {
  return {
    version: 1,
    layout: config.initial_layout,
    handled_run_id: null,
  };
}

function isPersistedWorkspaceState(
  value: unknown
): value is PersistedWorkspaceState {
  if (!value || typeof value !== "object") {
    return false;
  }
  const state = value as Partial<PersistedWorkspaceState>;
  return (
    state.version === 1 &&
    isWorkspaceLayout(state.layout) &&
    (state.handled_run_id === null || typeof state.handled_run_id === "string")
  );
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

function migrateLegacyLayout(value: unknown): WorkspaceLayout | null {
  if (!value || typeof value !== "object") {
    return null;
  }
  const legacy = value as {
    mode?: unknown;
    editorOpen?: unknown;
    previewOpen?: unknown;
  };
  if (
    (legacy.mode !== "about" && legacy.mode !== "work") ||
    typeof legacy.editorOpen !== "boolean" ||
    typeof legacy.previewOpen !== "boolean"
  ) {
    return null;
  }
  if (legacy.mode === "about") {
    if (legacy.previewOpen) {
      return splitLayout("about", "preview");
    }
    return singleLayout("about");
  }
  if (legacy.editorOpen && legacy.previewOpen) {
    return splitLayout("editor", "preview");
  }
  if (legacy.previewOpen) {
    return singleLayout("preview");
  }
  return singleLayout("editor");
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

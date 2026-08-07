export type WorkView = "edit" | "preview" | "split";
export type RecipeView = "about" | WorkView;
export type WorkPane = "editor" | "preview";

export type PaneLayout = {
  mode: "about" | "work";
  editorOpen: boolean;
  previewOpen: boolean;
};

/** What the workspace puts on screen, which is not always the layout the user picked.
 *
 * A config pane can ask for the whole row - Deploy does, being a wide surface that carries a
 * web preview of its own, so pairing it with the chat preview leaves both cramped. The stored
 * layout is left untouched, so leaving that pane restores whatever split was in force.
 */
export function shownLayout(
  layout: PaneLayout,
  editorFullWidth: boolean
): PaneLayout {
  if (!editorFullWidth || layout.mode !== "work" || !layout.editorOpen) {
    return layout;
  }
  return { ...layout, previewOpen: false };
}

/** A pane's share of the row: the whole of it, the larger half, the smaller half, or none. */
export type PaneRole = "closed" | "solo" | "major" | "minor";

export type PaneRoles = Record<"about" | "editor" | "preview", PaneRole>;

/** Which pane takes what, for one layout.
 *
 * The preview pairs with whichever of About or Editor is showing - that one is the major
 * half, the preview the minor - and any pane without company is solo. Stated once here and
 * handed to the panes as a class, rather than left for CSS to infer from which workspace-
 * level classes are present: "the preview is alone" then reads as "the preview without the
 * editor", which is wrong the moment About is what it is sharing the row with.
 */
export function paneRolesForLayout(layout: PaneLayout): PaneRoles {
  const aboutOpen = layout.mode === "about";
  const editorOpen = layout.mode === "work" && layout.editorOpen;
  const paired = layout.previewOpen && (aboutOpen || editorOpen);
  return {
    about: paneRole(aboutOpen, paired ? "major" : "solo"),
    editor: paneRole(editorOpen, paired ? "major" : "solo"),
    preview: paneRole(layout.previewOpen, paired ? "minor" : "solo"),
  };
}

function paneRole(open: boolean, openRole: PaneRole): PaneRole {
  return open ? openRole : "closed";
}

export function paneVisibility(hydrated: boolean): "hidden" | "visible" {
  if (!hydrated) {
    return "hidden";
  }
  return "visible";
}

export function workspaceTargetForView(
  workspaceActive: boolean,
  workspaceHref: string
): string | null {
  if (workspaceActive || !workspaceHref) {
    return null;
  }
  return appRelativeHref(workspaceHref);
}

function appRelativeHref(href: string): string {
  if (!href.startsWith("http://") && !href.startsWith("https://")) {
    return href;
  }
  const url = new URL(href);
  return `${url.pathname}${url.search}${url.hash}`;
}

export function initialPaneLayout(
  storage: { getItem(key: string): string | null },
  storageKey: string,
  initialView: RecipeView,
  navigationState: unknown
): PaneLayout {
  const navigationView = recipeViewFromNavigationState(navigationState);
  if (navigationView) {
    return layoutForView(navigationView);
  }
  return storedPaneLayout(storage, storageKey, initialView);
}

export function recipeViewNavigationState(view: RecipeView): {
  recipeView: RecipeView;
} {
  return { recipeView: view };
}

export function recipeViewFromNavigationState(
  state: unknown
): RecipeView | null {
  if (!state || typeof state !== "object") {
    return null;
  }
  const { recipeView } = state as { recipeView?: unknown };
  if (
    recipeView === "about" ||
    recipeView === "edit" ||
    recipeView === "preview" ||
    recipeView === "split"
  ) {
    return recipeView;
  }
  return null;
}

export function clearRecipeViewNavigationState() {
  const historyState = window.history.state;
  const userState = historyState?.usr;
  if (
    !userState ||
    typeof userState !== "object" ||
    !("recipeView" in userState)
  ) {
    return;
  }
  const remainingUserState = {
    ...(userState as Record<string, unknown>),
  };
  delete remainingUserState.recipeView;
  let nextUserState: Record<string, unknown> | null = null;
  if (Object.keys(remainingUserState).length) {
    nextUserState = remainingUserState;
  }
  window.history.replaceState({ ...historyState, usr: nextUserState }, "");
}

export function layoutAfterSelectingView(
  _layout: PaneLayout,
  view: RecipeView
): PaneLayout {
  return layoutForView(view);
}

export function layoutForView(view: RecipeView): PaneLayout {
  switch (view) {
    case "about":
      return { mode: "about", editorOpen: true, previewOpen: true };
    case "edit":
      return { mode: "work", editorOpen: true, previewOpen: false };
    case "preview":
      return { mode: "work", editorOpen: false, previewOpen: true };
    case "split":
      return { mode: "work", editorOpen: true, previewOpen: true };
    default: {
      const exhaustiveView: never = view;
      return exhaustiveView;
    }
  }
}

export function viewForLayout(layout: PaneLayout): RecipeView {
  if (layout.mode === "about") {
    return "about";
  }
  if (layout.editorOpen && layout.previewOpen) {
    return "split";
  }
  if (layout.previewOpen) {
    return "preview";
  }
  return "edit";
}

export function selectedWorkspaceView(
  activeView: RecipeView,
  workspaceActive: boolean
): RecipeView | null {
  if (!workspaceActive) {
    return null;
  }
  return activeView;
}

export function viewAfterRun(
  activeView: RecipeView,
  isRunning: boolean
): RecipeView {
  if (isRunning) {
    return activeView;
  }
  if (activeView === "edit" || activeView === "about") {
    return "split";
  }
  return activeView;
}

export type WorkspaceControls = {
  addEdit: boolean;
  addPreview: boolean;
  mergePreview: boolean;
};

const NO_CONTROLS: WorkspaceControls = {
  addEdit: false,
  addPreview: false,
  mergePreview: false,
};

export function workspaceControlsForLayout(
  layout: PaneLayout,
  editorFullWidth = false
): WorkspaceControls {
  // A pane that has asked for the whole row is not offering to share it, so the controls
  // that would pair it with the preview go away rather than sit there undoing the request.
  if (editorFullWidth && layout.mode === "work" && layout.editorOpen) {
    return NO_CONTROLS;
  }
  if (layout.mode === "about") {
    return NO_CONTROLS;
  }
  if (layout.editorOpen && layout.previewOpen) {
    return {
      addEdit: false,
      addPreview: false,
      mergePreview: true,
    };
  }
  if (layout.editorOpen) {
    return {
      addEdit: false,
      addPreview: true,
      mergePreview: false,
    };
  }
  return {
    addEdit: layout.previewOpen,
    addPreview: false,
    mergePreview: false,
  };
}

export function collapsePane(layout: PaneLayout, pane: WorkPane): PaneLayout {
  if (layout.mode === "about") {
    if (pane === "preview" && layout.previewOpen) {
      return { ...layout, previewOpen: false };
    }
    return layout;
  }
  if (pane === "editor") {
    if (!layout.previewOpen) {
      return layout;
    }
    return { ...layout, editorOpen: false };
  }
  if (!layout.editorOpen) {
    return layout;
  }
  return { ...layout, previewOpen: false };
}

export function storedPaneLayout(
  storage: { getItem(key: string): string | null },
  storageKey: string,
  initialView: RecipeView
): PaneLayout {
  let stored: unknown = null;
  try {
    const serialized = storage.getItem(storageKey);
    if (serialized) {
      stored = JSON.parse(serialized);
    }
  } catch {
    // Storage can be unavailable or malformed.
  }
  return normalizePaneLayout(stored, initialView);
}

export function normalizePaneLayout(
  value: unknown,
  initialView: RecipeView
): PaneLayout {
  if (!isPaneLayout(value)) {
    return layoutForView(initialView);
  }
  if (!value.editorOpen && !value.previewOpen) {
    return layoutForView(initialView);
  }
  return value;
}

function isPaneLayout(value: unknown): value is PaneLayout {
  if (!value || typeof value !== "object") {
    return false;
  }
  const layout = value as Partial<PaneLayout>;
  return (
    (layout.mode === "about" || layout.mode === "work") &&
    typeof layout.editorOpen === "boolean" &&
    typeof layout.previewOpen === "boolean"
  );
}

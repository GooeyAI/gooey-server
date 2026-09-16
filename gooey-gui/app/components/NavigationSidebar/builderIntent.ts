import type { NavWorkflowItem } from "@gooey-types/navigation_sidebar_props";

import { appRelativeHref } from "../RecipeWorkspace/paneState";

// Opening a Builder chat from the rail is a one-time command, not a place the
// user can link to, so it travels as Remix navigation state instead of a url
// fragment. `NavigationSidebar` is the single consumer: it acts on the intent
// once the navigation has committed and then drops it, which is what keeps a
// later refresh or Back from re-opening a panel the user has since closed.
export type BuilderIntent = NonNullable<NavWorkflowItem["builder_intent"]>;

type BuilderNavigationState = { builderIntent: BuilderIntent };

export function builderNavigationState(
  item: NavWorkflowItem
): BuilderNavigationState | undefined {
  if (!item.builder_intent) return undefined;
  return { builderIntent: item.builder_intent };
}

/** Where the rail's Ask Gooey has to go before it can open, or null when the panel is on
 *  this page already.
 *
 *  The server sends an absolute app url and `navigate` wants a path - handed the absolute
 *  one it resolves it against the origin and 404s on `/http://host/agent/`. Bound to the
 *  prop in one named place so the relativizing cannot be left off at the call site.
 */
export function builderTargetHref(
  openHref: string | null | undefined
): string | null {
  return openHref ? appRelativeHref(openHref) : null;
}

/** The same command, for a link the rail builds itself rather than one the server declared:
 *  a tab that cannot hold the panel navigates to the workspace carrying this. */
export function builderOpenNavigationState(): BuilderNavigationState {
  return { builderIntent: "open" };
}

export function readBuilderIntent(state: unknown): BuilderIntent | null {
  if (!state || typeof state !== "object") return null;
  const { builderIntent } = state as Partial<BuilderNavigationState>;
  if (builderIntent !== "open") return null;
  return builderIntent;
}

// React Router stores `location.state` under `history.state.usr`. Remove only the
// consumed Builder intent so layout-v2 navigation state survives regardless of
// effect ordering.
export function clearBuilderIntent() {
  const historyState = window.history.state;
  if (!historyState?.usr) return;
  const nextUserState = navigationStateWithoutBuilderIntent(historyState.usr);
  window.history.replaceState({ ...historyState, usr: nextUserState }, "");
}

export function navigationStateWithoutBuilderIntent(
  state: unknown
): Record<string, unknown> | null {
  if (!state || typeof state !== "object") {
    return null;
  }
  const nextState = { ...(state as Record<string, unknown>) };
  delete nextState.builderIntent;
  if (!Object.keys(nextState).length) {
    return null;
  }
  return nextState;
}

import type { NavWorkflowItem } from "@gooey-types/navigation_sidebar_props";
import { navigationStateWithoutBuilderIntent } from "./builderNavigation";

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

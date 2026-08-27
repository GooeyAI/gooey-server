import { useLocation } from "@remix-run/react";
import { useCallback, useEffect, useLayoutEffect, useState } from "react";

import {
  clearRecipeViewNavigationState,
  collapsePane,
  foldForNarrowViewport,
  initialPaneLayout,
  layoutAfterSelectingView,
  layoutForView,
  normalizePaneLayout,
  recipeViewFromNavigationState,
  type PaneLayout,
  type RecipeView,
  type WorkPane,
} from "./paneState";

const EVENT_PREFIX = "gooey:recipe-layout:";
/** The counterpart of the `max-width: 991.98px` blocks in the stylesheets. */
const WIDE_QUERY = "(min-width: 992px)";
const useHydrationEffect =
  typeof window === "undefined" ? useEffect : useLayoutEffect;

export function usePaneLayout(
  storageKey: string,
  initialView: RecipeView,
  narrowPane: WorkPane = "preview"
) {
  const location = useLocation();
  const [layout, setLayout] = useState<PaneLayout>(() =>
    layoutForView(initialView)
  );
  const [hydratedStorageKey, setHydratedStorageKey] = useState<string | null>(
    null
  );
  const [isNarrow, setIsNarrow] = useState(false);

  const updateLayout = useCallback(
    (next: PaneLayout) => {
      setLayout(next);
      if (typeof window === "undefined") {
        return;
      }
      try {
        window.sessionStorage.setItem(storageKey, JSON.stringify(next));
      } catch {
        // Storage can be unavailable in private browsing; in-memory state still works.
      }
      window.dispatchEvent(
        new CustomEvent(EVENT_PREFIX + storageKey, { detail: next })
      );
    },
    [storageKey]
  );

  useHydrationEffect(() => {
    const navigationView = recipeViewFromNavigationState(location.state);
    const nextLayout = initialPaneLayout(
      window.sessionStorage,
      storageKey,
      initialView,
      location.state
    );
    setLayout(nextLayout);
    // Before paint, in the same commit as `hydrated`, which is what the panes wait on.
    setIsNarrow(!window.matchMedia(WIDE_QUERY).matches);
    if (navigationView) {
      try {
        window.sessionStorage.setItem(storageKey, JSON.stringify(nextLayout));
      } catch {
        // Storage can be unavailable; the one-time navigation still works in memory.
      }
      clearRecipeViewNavigationState();
    }
    setHydratedStorageKey(storageKey);

    const syncLayout = (event: Event) => {
      const next = (event as CustomEvent<PaneLayout>).detail;
      setLayout(normalizePaneLayout(next, initialView));
    };
    const eventName = EVENT_PREFIX + storageKey;
    window.addEventListener(eventName, syncLayout);
    return () => window.removeEventListener(eventName, syncLayout);
  }, [initialView, location.key, location.state, storageKey]);

  useEffect(() => {
    const wide = window.matchMedia(WIDE_QUERY);
    const sync = () => setIsNarrow(!wide.matches);
    wide.addEventListener("change", sync);
    return () => wide.removeEventListener("change", sync);
  }, []);

  // These act on the stored layout, not on what the viewport currently allows.
  const selectView = useCallback(
    (view: RecipeView) => {
      updateLayout(layoutAfterSelectingView(layout, view));
    },
    [layout, updateLayout]
  );

  const collapse = useCallback(
    (pane: WorkPane) => updateLayout(collapsePane(layout, pane)),
    [layout, updateLayout]
  );

  return {
    // What can be shown here; consumers compose `shownLayout` on top.
    layout: foldForNarrowViewport(layout, narrowPane, isNarrow),
    // What the user picked. The top bar needs both - see `activeTabView`.
    storedLayout: layout,
    hydrated: hydratedStorageKey === storageKey,
    isNarrow,
    selectView,
    collapse,
  };
}

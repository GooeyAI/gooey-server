import { useLocation } from "@remix-run/react";
import { useCallback, useEffect, useLayoutEffect, useState } from "react";

import {
  clearRecipeViewNavigationState,
  collapsePane,
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
const useHydrationEffect =
  typeof window === "undefined" ? useEffect : useLayoutEffect;

export function usePaneLayout(storageKey: string, initialView: RecipeView) {
  const location = useLocation();
  const [layout, setLayout] = useState<PaneLayout>(() =>
    layoutForView(initialView)
  );
  const [hydratedStorageKey, setHydratedStorageKey] = useState<string | null>(
    null
  );

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
    const wide = window.matchMedia("(min-width: 992px)");
    const keepLayoutOnScreen = () => {
      if (
        !wide.matches &&
        layout.mode === "work" &&
        layout.editorOpen &&
        layout.previewOpen
      ) {
        updateLayout(layoutForView("preview"));
      }
    };
    keepLayoutOnScreen();
    wide.addEventListener("change", keepLayoutOnScreen);
    return () => wide.removeEventListener("change", keepLayoutOnScreen);
  }, [layout, updateLayout]);

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
    layout,
    hydrated: hydratedStorageKey === storageKey,
    selectView,
    collapse,
  };
}

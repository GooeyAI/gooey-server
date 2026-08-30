import { useLocation } from "@remix-run/react";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useState,
} from "react";
import type { ReactNode } from "react";

import type { PageShellConfig } from "@gooey-types/recipe_workspace_props";
import {
  clearWorkspaceLayoutNavigationState,
  foldForNarrowViewport,
  initialWorkspaceState,
  type PersistedWorkspaceState,
  type WorkspaceLayout,
} from "./components/RecipeWorkspace/paneState";

type WorkspaceEntry = {
  value: PersistedWorkspaceState;
  hydrated: boolean;
  hydrationToken: string;
};

export type PanelEntry = {
  open: boolean;
  storageKey: string | null;
  hydrated: boolean;
  commanded: boolean;
};

type AppShellContextValue = {
  workspaces: Record<string, WorkspaceEntry>;
  setWorkspace: (key: string, entry: WorkspaceEntry) => void;
  hydrateWorkspace: (key: string, entry: WorkspaceEntry) => void;
  panels: Record<string, PanelEntry>;
  setPanel: (key: string, entry: PanelEntry) => void;
  setPanelOpen: (key: string, open: boolean) => void;
  navDrawerOpen: boolean;
  setNavDrawerOpen: (open: boolean) => void;
  isNarrow: boolean;
};

const AppShellContext = createContext<AppShellContextValue | null>(null);

const useHydrationEffect =
  typeof window === "undefined" ? useEffect : useLayoutEffect;

export function AppShellProvider({ children }: { children: ReactNode }) {
  const [workspaces, setWorkspaces] = useState<Record<string, WorkspaceEntry>>(
    {}
  );
  const [panels, setPanels] = useState<Record<string, PanelEntry>>({});
  const [navDrawerOpen, setNavDrawerOpen] = useState(false);
  const isNarrow = useNarrowViewport();

  const setWorkspace = useCallback((key: string, entry: WorkspaceEntry) => {
    setWorkspaces((current) => ({ ...current, [key]: entry }));
  }, []);

  const hydrateWorkspace = useCallback((key: string, entry: WorkspaceEntry) => {
    setWorkspaces((current) => {
      if (current[key]?.hydrationToken === entry.hydrationToken) {
        return current;
      }
      return { ...current, [key]: entry };
    });
  }, []);

  const setPanel = useCallback((key: string, entry: PanelEntry) => {
    setPanels((current) => ({ ...current, [key]: entry }));
  }, []);

  const setPanelOpen = useCallback((key: string, open: boolean) => {
    setPanels((current) => {
      const entry = current[key];
      const storageKey = entry?.storageKey ?? null;
      persistPanelOpen(storageKey, open);
      return {
        ...current,
        [key]: {
          open,
          storageKey,
          hydrated: entry?.hydrated ?? true,
          commanded: true,
        },
      };
    });
  }, []);

  return (
    <AppShellContext.Provider
      value={{
        workspaces,
        setWorkspace,
        hydrateWorkspace,
        panels,
        setPanel,
        setPanelOpen,
        navDrawerOpen,
        setNavDrawerOpen,
        isNarrow,
      }}
    >
      {children}
    </AppShellContext.Provider>
  );
}

export function useWorkspaceLayout(config: PageShellConfig) {
  const context = useAppShellContext();
  const location = useLocation();
  const entry = context.workspaces[config.storage_key];
  const fallback: PersistedWorkspaceState = {
    version: 1,
    layout: config.route_layout ?? config.initial_layout,
    handled_run_id: null,
  };
  const current = entry?.value ?? fallback;
  const isNarrow = context.isNarrow;

  useHydrationEffect(() => {
    const hydrationToken = [
      location.key,
      config.active_run_id ?? "",
      config.route_layout ? JSON.stringify(config.route_layout) : "",
    ].join(":");
    const next = initialWorkspaceState(
      config,
      window.sessionStorage,
      location.state
    );
    persistWorkspaceState(config.storage_key, next);
    context.hydrateWorkspace(config.storage_key, {
      value: next,
      hydrated: true,
      hydrationToken,
    });
    if (workspaceLayoutNavigationStatePresent(location.state)) {
      clearWorkspaceLayoutNavigationState();
    }
  }, [config.storage_key, config.active_run_id, location.key, location.state]);

  const selectLayout = useCallback(
    (layout: WorkspaceLayout) => {
      const next = { ...current, layout };
      persistWorkspaceState(config.storage_key, next);
      context.setWorkspace(config.storage_key, {
        value: next,
        hydrated: true,
        hydrationToken: entry?.hydrationToken ?? "",
      });
    },
    [config.storage_key, context, current]
  );

  return {
    layout: foldForNarrowViewport(
      current.layout,
      config.narrow_surface,
      isNarrow
    ),
    storedLayout: current.layout,
    hydrated: Boolean(entry?.hydrated),
    isNarrow,
    selectLayout,
  };
}

export function useAppShellPanel(
  key: string | null | undefined,
  defaultOpen = false,
  storageKey: string | null = null
) {
  const context = useAppShellContext();
  const entry = key ? context.panels[key] : undefined;
  const matchesStorage = entry?.storageKey === storageKey;
  const open = panelOpenForStorage(entry, storageKey, defaultOpen);

  useHydrationEffect(() => {
    if (!key) {
      return;
    }
    const current = context.panels[key];
    if (shouldAdoptPanelCommand(current, storageKey)) {
      persistPanelOpen(storageKey, current.open);
      context.setPanel(key, { ...current, storageKey });
      return;
    }
    if (!shouldRestorePanel(current, storageKey)) {
      return;
    }
    const restored = restorePanelOpen(storageKey, defaultOpen);
    context.setPanel(key, {
      open: restored,
      storageKey,
      hydrated: true,
      commanded: false,
    });
  }, [defaultOpen, key, storageKey]);

  const setOpen = useCallback(
    (nextOpen: boolean) => {
      if (!key) {
        return;
      }
      persistPanelOpen(storageKey, nextOpen);
      context.setPanel(key, {
        open: nextOpen,
        storageKey,
        hydrated: true,
        commanded: true,
      });
    },
    [context, key, storageKey]
  );

  return {
    open,
    hydrated: Boolean(matchesStorage && entry?.hydrated),
    setOpen,
  };
}

/** The shared breakpoint, for components outside the workspace that fold on the same width. */
export function useIsNarrowViewport(): boolean {
  return useAppShellContext().isNarrow;
}

export function useNavDrawer() {
  const context = useAppShellContext();
  return {
    open: context.navDrawerOpen,
    setOpen: context.setNavDrawerOpen,
  };
}

export function useAppShellPanelActions() {
  const context = useAppShellContext();
  return { setPanelOpen: context.setPanelOpen };
}

export function panelOpenForStorage(
  entry: PanelEntry | undefined,
  storageKey: string | null,
  defaultOpen: boolean
): boolean {
  if (entry?.storageKey !== storageKey) {
    return defaultOpen;
  }
  return entry.open;
}

export function shouldRestorePanel(
  entry: PanelEntry | undefined,
  storageKey: string | null
): boolean {
  return !entry || entry.storageKey !== storageKey || !entry.commanded;
}

export function shouldAdoptPanelCommand(
  entry: PanelEntry | undefined,
  storageKey: string | null
): entry is PanelEntry {
  return Boolean(entry?.commanded && entry.storageKey === null && storageKey);
}

function useAppShellContext(): AppShellContextValue {
  const context = useContext(AppShellContext);
  if (!context) {
    throw new Error("App shell hooks require AppShellProvider");
  }
  return context;
}

const WIDE_QUERY = "(min-width: 992px)";

/** The one answer to "is this a phone", shared by everything that folds on it.
 *
 *  It used to be `useState(false)` inside `useWorkspaceLayout`, which every consumer calls
 *  separately - the top bar, the workspace, each pane trigger, the run bar - so each held its
 *  own copy, corrected by its own listener from its own effect. They could disagree, and then
 *  the bar reasoned about one layout while the workspace drew another.
 *
 *  Called once, by the provider, and handed down: one listener, and one value every consumer
 *  reads in the same render. `false` until the effect runs, which is the wide layout the
 *  markup is authored for and what the server renders.
 *
 *  Plain state and an effect rather than `useSyncExternalStore`: this app is on React 17,
 *  where that hook does not exist - importing it yields `undefined` and calling it throws
 *  while rendering on the server. */
function useNarrowViewport(): boolean {
  const [isNarrow, setIsNarrow] = useState(false);

  useEffect(() => {
    const wide = window.matchMedia(WIDE_QUERY);
    const sync = () => setIsNarrow(!wide.matches);
    sync();
    wide.addEventListener("change", sync);
    return () => wide.removeEventListener("change", sync);
  }, []);

  return isNarrow;
}

function persistWorkspaceState(
  storageKey: string,
  state: PersistedWorkspaceState
) {
  try {
    window.sessionStorage.setItem(storageKey, JSON.stringify(state));
  } catch {
    // The in-memory context remains usable when browser storage is unavailable.
  }
}

function workspaceLayoutNavigationStatePresent(state: unknown): boolean {
  return Boolean(
    state && typeof state === "object" && "workspaceLayout" in state
  );
}

function restorePanelOpen(
  storageKey: string | null,
  defaultOpen: boolean
): boolean {
  if (!storageKey) {
    return defaultOpen;
  }
  try {
    const stored = window.sessionStorage.getItem(storageKey);
    if (stored !== null) {
      return stored === "true";
    }
  } catch {
    return defaultOpen;
  }
  return defaultOpen;
}

function persistPanelOpen(storageKey: string | null, open: boolean) {
  if (!storageKey) {
    return;
  }
  try {
    window.sessionStorage.setItem(storageKey, String(open));
  } catch {
    // The in-memory context remains usable when browser storage is unavailable.
  }
}

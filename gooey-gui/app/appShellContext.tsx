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
  workspaceLayoutFromNavigationState,
} from "./components/RecipeWorkspace/paneState";

type WorkspaceEntry = {
  value: PersistedWorkspaceState;
  hydrated: boolean;
  hydrationToken: string;
  hadStoredLayout: boolean;
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

  // One matchMedia subscription for the whole shell. Every consumer of the breakpoint - the
  // top bar, the workspace, the nav rail - reads this, so they cannot disagree about which
  // side of it the viewport is on, and none of them binds a listener of its own.
  // False until mounted: the server cannot know the viewport, and the panes stay hidden
  // until hydration anyway.
  const [isNarrow, setIsNarrow] = useState(false);
  useHydrationEffect(() => {
    const wide = window.matchMedia(WIDE_QUERY);
    const sync = () => setIsNarrow(!wide.matches);
    sync();
    wide.addEventListener("change", sync);
    return () => wide.removeEventListener("change", sync);
  }, []);

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

/** The current state of one workspace, and the one way to change it.
 *
 * Read-and-write, but it does not hydrate: a component that only needs to switch the layout
 * (a deep link, a card that opens a pane) uses this and leaves the reading of storage and
 * navigation state to the components that own the workspace. */
export function useWorkspaceLayoutActions(config: PageShellConfig) {
  const context = useAppShellContext();
  const entry = context.workspaces[config.storage_key];
  const current: PersistedWorkspaceState = entry?.value ?? {
    version: 1,
    layout: config.route_layout ?? config.initial_layout,
    handled_run_id: null,
  };

  const selectLayout = useCallback(
    (layout: WorkspaceLayout) => {
      const next = { ...current, layout };
      persistWorkspaceState(config.storage_key, next);
      context.setWorkspace(config.storage_key, {
        value: next,
        hydrated: true,
        hydrationToken: entry?.hydrationToken ?? "",
        hadStoredLayout: true,
      });
    },
    [config.storage_key, context, current, entry?.hydrationToken]
  );

  return { entry, current, selectLayout };
}

/** The full workspace hook: everything `useWorkspaceLayoutActions` gives, plus the effect
 *  that seeds the layout from storage, the url and navigation state on each navigation.
 *
 *  Only the components that render the workspace itself - the top bar and the pane grid -
 *  should call this. */
export function useWorkspaceLayout(config: PageShellConfig) {
  const context = useAppShellContext();
  const location = useLocation();
  const { entry, current, selectLayout } = useWorkspaceLayoutActions(config);
  const isNarrow = context.isNarrow;

  useHydrationEffect(() => {
    const hydrationToken = [
      location.key,
      config.active_run_id ?? "",
      config.route_layout ? JSON.stringify(config.route_layout) : "",
    ].join(":");
    const hadStoredLayout =
      hasStoredWorkspaceState(config.storage_key) ||
      Boolean(config.route_layout) ||
      Boolean(workspaceLayoutFromNavigationState(location.state));
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
      hadStoredLayout,
    });
    if (workspaceLayoutNavigationStatePresent(location.state)) {
      clearWorkspaceLayoutNavigationState();
    }
  }, [config.storage_key, config.active_run_id, location.key, location.state]);

  return {
    layout: foldForNarrowViewport(
      current.layout,
      config.narrow_surface,
      isNarrow
    ),
    storedLayout: current.layout,
    hydrated: Boolean(entry?.hydrated),
    hadStoredLayout: Boolean(entry?.hadStoredLayout),
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

/** True below the shell's breakpoint, where the rail becomes a drawer and split panes fold
 *  to one. Backed by the provider's single matchMedia subscription. */
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

function hasStoredWorkspaceState(storageKey: string): boolean {
  try {
    return window.sessionStorage.getItem(storageKey) !== null;
  } catch {
    return false;
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

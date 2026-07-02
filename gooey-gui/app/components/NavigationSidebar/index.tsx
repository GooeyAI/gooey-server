import "./NavigationSidebar.css";

import clsx from "clsx";
import type { CustomComponentProps } from "~/components";
import type {
  NavAccountData,
  NavigationSidebarProps,
} from "@gooey-types/navigation_sidebar_props";
import { useState, useEffect, useRef } from "react";
import { AccountSection } from "./AccountSection";
import {
  BUILDER_SIDEBAR_KEY,
  GooeyBuilderButton,
  OPEN_BUILDER_HASH,
} from "./GooeyBuilderButton";
import { NavigationHeader, NavigationHeaderMobile } from "./NavigationHeader";
import { PrimaryNavItems } from "./PrimaryNavItems";

const NAV_COLLAPSED_KEY = "nav-sidebar:default-collapsed";
// Keep in sync with SWITCH_WORKSPACE_KEY in workspaces/widgets.py
const SWITCH_WORKSPACE_KEY = "--switch-workspace";
// Below this width the rail becomes an off-canvas drawer (matches the CSS
// breakpoint in NavigationSidebar.css).
const MOBILE_MEDIA_QUERY = "(max-width: 991.98px)";

export function NavigationSidebar({
  logo_image_url,
  nav_items,
  active_key,
  default_collapsed,
  recent_workflows,
  account,
  gooey_builder,
  onChange,
  state,
}: CustomComponentProps & NavigationSidebarProps) {
  const builderInitiallyOpen = Boolean(state[BUILDER_SIDEBAR_KEY]);
  const [collapsed, setCollapsed] = useState(
    builderInitiallyOpen || default_collapsed
  );
  const [isMobile, setIsMobile] = useState(false);
  const [builderOpen, setBuilderOpen] = useState(builderInitiallyOpen);
  const mounted = useRef(false);

  const railCollapsed = !isMobile && collapsed;
  const drawerOpen = isMobile && !collapsed;

  useEffect(() => {
    if (isMobile || builderOpen) return;
    if (!mounted.current) {
      mounted.current = true;
      if (state[NAV_COLLAPSED_KEY] === collapsed) return;
    }
    state[NAV_COLLAPSED_KEY] = collapsed;
    onChange();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [collapsed, isMobile, builderOpen]);

  useEffect(() => {
    const mq = window.matchMedia(MOBILE_MEDIA_QUERY);
    const update = () => {
      setIsMobile(mq.matches);
      // Entering mobile always starts with the drawer closed (batched with the
      // isMobile update so `drawerOpen` never flips true in between).
      if (mq.matches) setCollapsed(true);
    };
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    const onOpen = () => {
      setBuilderOpen(true);
      setCollapsed(true);
    };
    const onClose = () => {
      setBuilderOpen(false);
      // Closing the Builder re-expands the rail on desktop, but must not pop
      // the drawer open on mobile.
      if (!isMobileViewport()) setCollapsed(false);
    };
    window.addEventListener(`${BUILDER_SIDEBAR_KEY}:open`, onOpen);
    window.addEventListener(`${BUILDER_SIDEBAR_KEY}:close`, onClose);
    return () => {
      window.removeEventListener(`${BUILDER_SIDEBAR_KEY}:open`, onOpen);
      window.removeEventListener(`${BUILDER_SIDEBAR_KEY}:close`, onClose);
    };
  }, []);

  // Opening a Builder run from the rail lands with an `#open-builder` fragment;
  // force-open the Builder panel (overriding any persisted state), then strip
  // the fragment so a later refresh doesn't re-open it.
  useEffect(() => {
    function handleOpenBuilderHash() {
      if (window.location.hash !== OPEN_BUILDER_HASH) return;
      window.history.replaceState(
        null,
        "",
        window.location.pathname + window.location.search
      );
      setTimeout(() => {
        window.dispatchEvent(new CustomEvent(`${BUILDER_SIDEBAR_KEY}:open`));
      }, 500);
    }
    // Defer the initial check so Sidebar.tsx registers its open listener first.
    const timer = window.setTimeout(handleOpenBuilderHash, 0);
    window.addEventListener("hashchange", handleOpenBuilderHash);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("hashchange", handleOpenBuilderHash);
    };
  }, []);

  const expandRail = (e?: React.MouseEvent) => {
    e?.preventDefault();
    setCollapsed(false);
  };

  const switchWorkspace = (workspaceId: number) => {
    state[SWITCH_WORKSPACE_KEY] = String(workspaceId);
    onChange();
  };

  const navClass = clsx(
    "nav-sidebar d-flex flex-column border-end bg-body",
    railCollapsed && "nav-sidebar--collapsed",
    drawerOpen && "nav-sidebar--drawer-open"
  );

  return (
    <div>
      <NavigationHeaderMobile
        logo_image_url={logo_image_url}
        isMobile={isMobile}
        drawerOpen={drawerOpen}
        onDrawerOpen={() => setCollapsed(false)}
        onDrawerClose={() => setCollapsed(true)}
        gooey_builder={gooey_builder}
        builderOpen={builderOpen}
        account={account}
        onSwitchWorkspace={switchWorkspace}
      />

      <nav
        className={navClass}
        onClick={railCollapsed ? () => expandRail() : undefined}
      >
        <NavigationHeader
          logo_image_url={logo_image_url}
          railCollapsed={railCollapsed}
          isMobile={isMobile}
          onExpand={expandRail}
          onCollapse={() => setCollapsed(true)}
          onDrawerClose={() => setCollapsed(true)}
        />

        <PrimaryNavItems
          nav_items={nav_items}
          active_key={active_key}
          recent_workflows={recent_workflows}
          account={account}
          railCollapsed={railCollapsed}
        />

        <NavigationFooter
          gooey_builder={gooey_builder}
          railCollapsed={railCollapsed}
          builderOpen={builderOpen}
          isMobile={isMobile}
          account={account}
          onSwitchWorkspace={switchWorkspace}
        />
      </nav>
    </div>
  );
}

function NavigationFooter({
  gooey_builder,
  railCollapsed,
  builderOpen,
  isMobile,
  account,
  onSwitchWorkspace,
}: {
  gooey_builder: NavigationSidebarProps["gooey_builder"];
  railCollapsed: boolean;
  builderOpen: boolean;
  isMobile: boolean;
  account: NavAccountData;
  onSwitchWorkspace: (workspaceId: number) => void;
}) {
  return (
    <div className="flex-shrink-0 p-2 d-flex flex-column gap-2">
      {/* On mobile the Gooey Builder launcher lives in the top bar, not the drawer. */}
      {gooey_builder && !builderOpen && !isMobile && (
        <GooeyBuilderButton
          gooey_builder={gooey_builder}
          compact={railCollapsed}
        />
      )}
      {/* On mobile the account menu lives in the top bar, not the drawer. */}
      {!isMobile && (
        <div className="border-top pt-2">
          <AccountSection
            account={account}
            onSwitchWorkspace={onSwitchWorkspace}
            compact={railCollapsed}
            placement="top-start"
          />
        </div>
      )}
    </div>
  );
}

function isMobileViewport() {
  if (typeof window === "undefined") return false;
  return window.matchMedia(MOBILE_MEDIA_QUERY).matches;
}

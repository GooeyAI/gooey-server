import "~/styles/gooey-orbit-border.css";
import "./NavigationSidebar.css";

import clsx from "clsx";
import { useLocation } from "@remix-run/react";
import type { CustomComponentProps } from "~/components";
import type {
  NavAccountData,
  NavigationSidebarProps,
} from "@gooey-types/navigation_sidebar_props";
import { useState, useEffect, useRef } from "react";
import { useAppShellPanelValue, useNavDrawer } from "~/appShellContext";
import { AccountSection } from "./AccountSection";
import { clearBuilderIntent, readBuilderIntent } from "./builderIntent";
import { GooeyBuilderButton } from "./GooeyBuilderButton";
import { NavigationHeader, NavigationHeaderMobile } from "./NavigationHeader";
import { PrimaryNavItems } from "./PrimaryNavItems";

// Below this width the rail becomes an off-canvas drawer (matches the CSS
// breakpoint in NavigationSidebar.css).
const MOBILE_MEDIA_QUERY = "(max-width: 991.98px)";

export function NavigationSidebar({
  logo_image_url,
  logo_href,
  nav_items,
  active_key,
  collapsed_state_key,
  default_collapsed,
  account,
  gooey_builder,
  onChange,
  state,
}: CustomComponentProps & NavigationSidebarProps) {
  const location = useLocation();
  const builderEventKey = gooey_builder?.event_key;
  const builderInitiallyOpen = Boolean(
    builderEventKey && state[builderEventKey]
  );
  const builder = useAppShellPanelValue(builderEventKey, builderInitiallyOpen);
  const navDrawer = useNavDrawer();
  const [collapsed, setCollapsed] = useState(
    builderInitiallyOpen || default_collapsed
  );
  const [isMobile, setIsMobile] = useState(false);
  const mounted = useRef(false);

  const railCollapsed = !isMobile && collapsed;
  const drawerOpen = isMobile && navDrawer.open;

  useEffect(() => {
    if (isMobile || builder.open) return;
    if (!mounted.current) {
      mounted.current = true;
      if (state[collapsed_state_key] === collapsed) return;
    }
    state[collapsed_state_key] = collapsed;
    onChange();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [collapsed, isMobile, builder.open, collapsed_state_key]);

  useEffect(() => {
    if (builder.open) {
      setCollapsed(true);
    }
  }, [builder.open]);

  useEffect(() => {
    const mq = window.matchMedia(MOBILE_MEDIA_QUERY);
    const update = () => {
      setIsMobile(mq.matches);
      if (mq.matches) {
        navDrawer.setOpen(false);
      }
    };
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);

  // The mobile drawer covers the page, so navigating out of it has to close it:
  // a nav item, a history row, a link in the account menu. Taps that navigate
  // nowhere -- opening the account menu, switching workspace, toggling a section
  // open -- leave the drawer where it is.
  useEffect(() => {
    if (isMobile) {
      navDrawer.setOpen(false);
    }
  }, [isMobile, location.key]);

  const builderIntent = readBuilderIntent(location.state);
  useEffect(() => {
    if (!builderEventKey || !builderIntent) {
      return;
    }
    clearBuilderIntent();
    builder.setOpen(true);
    setCollapsed(true);
  }, [builderEventKey, builderIntent, location.key]);

  const expandRail = (e?: React.MouseEvent) => {
    e?.preventDefault();
    setCollapsed(false);
  };

  const switchWorkspace = (workspaceId: number) => {
    if (!account.switch_workspace_key) return;
    state[account.switch_workspace_key] = String(workspaceId);
    onChange();
  };

  const navClass = clsx(
    "nav-sidebar d-flex flex-column border-end",
    railCollapsed && "nav-sidebar--collapsed",
    drawerOpen && "nav-sidebar--drawer-open"
  );

  return (
    <div>
      <NavigationHeaderMobile
        logo_image_url={logo_image_url}
        logo_href={logo_href}
        isMobile={isMobile}
        drawerOpen={drawerOpen}
        onDrawerOpen={() => navDrawer.setOpen(true)}
        onDrawerClose={() => navDrawer.setOpen(false)}
        gooey_builder={gooey_builder}
        builderOpen={builder.open}
        account={account}
        onSwitchWorkspace={switchWorkspace}
        onBuilderOpen={() => builder.setOpen(true)}
      />

      <nav
        className={navClass}
        onClick={railCollapsed ? () => expandRail() : undefined}
      >
        <NavigationHeader
          logo_image_url={logo_image_url}
          logo_href={logo_href}
          railCollapsed={railCollapsed}
          isMobile={isMobile}
          onExpand={expandRail}
          onCollapse={() => setCollapsed(true)}
          onDrawerClose={() => navDrawer.setOpen(false)}
        />

        <PrimaryNavItems
          nav_items={nav_items}
          active_key={active_key}
          account={account}
          railCollapsed={railCollapsed}
        />

        <NavigationFooter
          gooey_builder={gooey_builder}
          railCollapsed={railCollapsed}
          builderOpen={builder.open}
          isMobile={isMobile}
          account={account}
          onSwitchWorkspace={switchWorkspace}
          onBuilderOpen={() => builder.setOpen(true)}
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
  onBuilderOpen,
}: {
  gooey_builder: NavigationSidebarProps["gooey_builder"];
  railCollapsed: boolean;
  builderOpen: boolean;
  isMobile: boolean;
  account: NavAccountData;
  onSwitchWorkspace: (workspaceId: number) => void;
  onBuilderOpen: () => void;
}) {
  return (
    <div className="flex-shrink-0 px-2 pb-2 d-flex flex-column gap-2">
      {gooey_builder && !builderOpen && (
        <GooeyBuilderButton
          gooey_builder={gooey_builder}
          compact={railCollapsed}
          onOpen={onBuilderOpen}
        />
      )}
      <div className="border-top pt-2">
        <AccountSection
          account={account}
          onSwitchWorkspace={onSwitchWorkspace}
          compact={railCollapsed}
          placement="top-start"
        />
      </div>
    </div>
  );
}

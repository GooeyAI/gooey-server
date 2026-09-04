import "~/styles/gooey-orbit-border.css";
import "./NavigationSidebar.css";

import clsx from "clsx";
import { useLocation, useNavigate } from "@remix-run/react";
import type { CustomComponentProps } from "~/components";
import type {
  NavAccountData,
  NavigationSidebarProps,
} from "@gooey-types/navigation_sidebar_props";
import { useState, useEffect, useRef } from "react";
import { useAppShellPanel, useNavDrawer } from "~/appShellContext";
import { AccountSection } from "./AccountSection";
import {
  builderOpenNavigationState,
  builderTargetHref,
  clearBuilderIntent,
  readBuilderIntent,
} from "./builderIntent";
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
  const navigate = useNavigate();
  const builderEventKey = gooey_builder?.event_key;
  // Where to open the panel when this page cannot hold it - Deploy, API and Usage have no
  // workspace beside it. Set means the panel is not here, whatever the last state of it
  // was: the rail goes on offering the way in, and does not collapse for it.
  const builderElsewhere = builderTargetHref(gooey_builder?.open_href);
  const builderInitiallyOpen = Boolean(
    builderEventKey && state[builderEventKey] && !builderElsewhere
  );
  const builder = useAppShellPanel(
    builderEventKey,
    builderInitiallyOpen,
    gooey_builder?.storage_key ?? null
  );
  // Open *here*: a page that cannot hold the panel is not showing it, whatever the panel's
  // last state was - so the rail keeps offering the way in rather than hiding the button
  // for something that is not on screen.
  const builderOpenHere = builder.open && !builderElsewhere;
  const navDrawer = useNavDrawer();
  const [collapsed, setCollapsed] = useState(
    builderInitiallyOpen || default_collapsed
  );
  const [isMobile, setIsMobile] = useState(false);
  const mounted = useRef(false);

  const railCollapsed = !isMobile && collapsed;
  const drawerOpen = isMobile && navDrawer.open;

  // `builder.open` is read here but is deliberately not a dependency. `onChange` posts the
  // whole form, and a post started in the same tick as a link click supersedes that link's
  // navigation - listed, this ran on every close of Ask Gooey, so clicking Usage closed the
  // panel and went nowhere. Only a change of `collapsed` itself should persist anything.
  useEffect(() => {
    if (isMobile || builder.open) return;
    if (!mounted.current) {
      mounted.current = true;
      if (state[collapsed_state_key] === collapsed) return;
    }
    state[collapsed_state_key] = collapsed;
    onChange();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [collapsed, isMobile, collapsed_state_key]);

  // Ask Gooey takes the room the nav was in: the rail collapses, and the drawer - which is
  // the whole screen below lg, and above the panel in the stack - goes entirely, or the
  // panel it just opened would be behind it. Only on the change, so reopening the nav over
  // an open panel to navigate somewhere still works.
  useEffect(() => {
    if (builder.open) {
      setCollapsed(true);
      navDrawer.setOpen(false);
    }
  }, [builder.open]);

  useEffect(() => {
    if (!builderEventKey) {
      return;
    }
    const onChanged = (event: Event) => {
      const open = (event as CustomEvent<{ open?: boolean }>).detail?.open;
      if (typeof open === "boolean") {
        builder.setOpen(open);
      }
    };
    window.addEventListener(`${builderEventKey}:changed`, onChanged);
    return () => {
      window.removeEventListener(`${builderEventKey}:changed`, onChanged);
    };
  }, [builderEventKey]);

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
  //
  // Watched on the url rather than on `location.key`, which is minted afresh by every
  // navigation - and this app posts its whole form as one, on every edit and on every tick
  // of a streaming run. Each of those shut the drawer, so it could not be held open at all
  // while a run was going.
  const route = `${location.pathname}${location.search}`;
  useEffect(() => {
    if (isMobile) {
      navDrawer.setOpen(false);
    }
  }, [isMobile, route]);

  const builderIntent = readBuilderIntent(location.state);
  useEffect(() => {
    if (!builderEventKey || !builderIntent) {
      return;
    }
    clearBuilderIntent();
    builder.setOpen(true);
    setCollapsed(true);
  }, [builderEventKey, builderIntent, location.key]);

  // The intent rides along as navigation state, which the effect above acts on once the
  // next page has committed - the same path the rail's saved-workflow links take.
  const openBuilder = () => {
    if (builderElsewhere) {
      navigate(builderElsewhere, { state: builderOpenNavigationState() });
      return;
    }
    builder.setOpen(true);
  };

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
        builderOpen={builderOpenHere}
        account={account}
        onSwitchWorkspace={switchWorkspace}
        onBuilderOpen={openBuilder}
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
          builderOpen={builderOpenHere}
          isMobile={isMobile}
          account={account}
          onSwitchWorkspace={switchWorkspace}
          onBuilderOpen={openBuilder}
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

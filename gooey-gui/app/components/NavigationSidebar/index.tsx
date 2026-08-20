import "./NavigationSidebar.css";

import clsx from "clsx";
import { useLocation } from "@remix-run/react";
import type { CustomComponentProps } from "~/components";
import type {
  NavAccountData,
  NavigationSidebarProps,
} from "@gooey-types/navigation_sidebar_props";
import { useState, useEffect, useRef } from "react";
import { AccountSection } from "./AccountSection";
import { builderOpenEventName } from "./builderNavigation";
import { clearBuilderIntent, readBuilderIntent } from "./builderIntent";
import { GooeyBuilderButton } from "./GooeyBuilderButton";
import { NavigationHeader, NavigationHeaderMobile } from "./NavigationHeader";
import { NAV_DRAWER_OPEN_EVENT } from "./navDrawer";
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
      if (state[collapsed_state_key] === collapsed) return;
    }
    state[collapsed_state_key] = collapsed;
    onChange();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [collapsed, isMobile, builderOpen, collapsed_state_key]);

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
    if (!builderEventKey) return;
    const onOpen = () => {
      setBuilderOpen(true);
      setCollapsed(true);
    };
    const onClose = () => {
      setBuilderOpen(false);
    };
    // The panel's settled state, which outranks the commands above: a command says what should
    // happen and can be dispatched before the panel is listening, while this says what the
    // panel actually is. Without it the rail could sit on a stale `true` - the panel closed,
    // its button still withheld - until a reload reset this state from the server's.
    const onChanged = (e: Event) => {
      const open = (e as CustomEvent<{ open?: boolean }>).detail?.open;
      if (typeof open === "boolean") setBuilderOpen(open);
    };
    window.addEventListener(`${builderEventKey}:open`, onOpen);
    window.addEventListener(`${builderEventKey}:close`, onClose);
    window.addEventListener(`${builderEventKey}:changed`, onChanged);
    return () => {
      window.removeEventListener(`${builderEventKey}:open`, onOpen);
      window.removeEventListener(`${builderEventKey}:close`, onClose);
      window.removeEventListener(`${builderEventKey}:changed`, onChanged);
    };
  }, [builderEventKey]);

  // A Builder-chat row in the rail carries an "open" intent as navigation state.
  // This effect runs once the navigation has committed, so the panel is already
  // listening; consuming the intent here also clears it, leaving refreshes and
  // Back to honour whatever the user last chose. Nothing ever closes the panel
  // on the user's behalf.
  const builderIntent = readBuilderIntent(location.state);
  const builderOpenEvent = builderOpenEventName(builderEventKey, builderIntent);
  useEffect(() => {
    if (!builderOpenEvent) return;
    clearBuilderIntent();
    window.dispatchEvent(new CustomEvent(builderOpenEvent));
  }, [builderOpenEvent, location.key]);

  // The control that opens the drawer lives in RecipeTopBar now, which is a sibling with no
  // common ancestor to lift this state into - hence an event rather than a prop. Open only:
  // closing is the scrim's and the header's job, both of which are inside this component.
  useEffect(() => {
    const onOpen = () => setCollapsed(false);
    window.addEventListener(NAV_DRAWER_OPEN_EVENT, onOpen);
    return () => window.removeEventListener(NAV_DRAWER_OPEN_EVENT, onOpen);
  }, []);

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
    "nav-sidebar d-flex flex-column border-end bg-body",
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
          logo_href={logo_href}
          railCollapsed={railCollapsed}
          isMobile={isMobile}
          onExpand={expandRail}
          onCollapse={() => setCollapsed(true)}
          onDrawerClose={() => setCollapsed(true)}
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
    <div className="flex-shrink-0 px-2 pb-2 d-flex flex-column gap-2">
      {gooey_builder && !builderOpen && (
        <GooeyBuilderButton
          gooey_builder={gooey_builder}
          compact={railCollapsed}
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

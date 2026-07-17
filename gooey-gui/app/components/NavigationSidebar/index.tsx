import "./NavigationSidebar.css";

import clsx from "clsx";
import type { CustomComponentProps } from "~/components";
import type {
  NavAccountData,
  NavigationSidebarProps,
} from "@gooey-types/navigation_sidebar_props";
import { useState, useEffect, useRef } from "react";
import { AccountSection } from "./AccountSection";
import { GooeyBuilderButton } from "./GooeyBuilderButton";
import { NavigationHeader, NavigationHeaderMobile } from "./NavigationHeader";
import { PrimaryNavItems } from "./PrimaryNavItems";

// Below this width the rail becomes an off-canvas drawer (matches the CSS
// breakpoint in NavigationSidebar.css).
const MOBILE_MEDIA_QUERY = "(max-width: 991.98px)";

export function NavigationSidebar({
  logo_image_url,
  nav_items,
  active_key,
  collapsed_state_key,
  default_collapsed,
  account,
  gooey_builder,
  onChange,
  state,
}: CustomComponentProps & NavigationSidebarProps) {
  const builderEventKey = gooey_builder?.event_key;
  const builderOpenHash = gooey_builder?.open_hash;
  const builderInitiallyOpen = Boolean(
    builderEventKey && state[builderEventKey]
  );
  const [collapsed, setCollapsed] = useState(
    builderInitiallyOpen || default_collapsed
  );
  const [isMobile, setIsMobile] = useState(false);
  const [builderOpen, setBuilderOpen] = useState(builderInitiallyOpen);
  const builderOpenRef = useRef(builderInitiallyOpen);
  builderOpenRef.current = builderOpen;
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
    window.addEventListener(`${builderEventKey}:open`, onOpen);
    window.addEventListener(`${builderEventKey}:close`, onClose);
    return () => {
      window.removeEventListener(`${builderEventKey}:open`, onOpen);
      window.removeEventListener(`${builderEventKey}:close`, onClose);
    };
  }, [builderEventKey]);

  // Opening a Builder run from the rail lands with the configured fragment.
  // Force-open the Builder panel (overriding any persisted state), then strip
  // the fragment so a later refresh doesn't re-open it.
  useEffect(() => {
    if (!builderEventKey || !builderOpenHash) return;
    function handleOpenBuilderHash() {
      if (window.location.hash == builderOpenHash) {
        window.history.replaceState(
          null,
          "",
          window.location.pathname + window.location.search
        );
        setTimeout(() => {
          window.dispatchEvent(new CustomEvent(`${builderEventKey}:open`));
        }, 500);
      } else {
        if (builderOpenRef.current) {
          setTimeout(() => {
            window.dispatchEvent(new CustomEvent(`${builderEventKey}:close`));
            setBuilderOpen(false);
          }, 500);
        }
      }
    }
    // Defer the initial check so Sidebar.tsx registers its open listener first.
    const timer = window.setTimeout(handleOpenBuilderHash, 0);
    window.addEventListener("hashchange", handleOpenBuilderHash);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("hashchange", handleOpenBuilderHash);
    };
  }, [builderEventKey, builderOpenHash]);

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
        isMobile={isMobile}
        drawerOpen={drawerOpen}
        onDrawerOpen={() => setCollapsed(false)}
        onDrawerClose={() => setCollapsed(true)}
        gooey_builder={gooey_builder}
        builderOpen={builderOpen}
        account={account}
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
      {/* On mobile the Gooey Builder launcher lives in the top bar, not the drawer. */}
      {gooey_builder && !builderOpen && !isMobile && (
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

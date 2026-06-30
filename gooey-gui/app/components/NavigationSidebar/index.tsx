import "./NavigationSidebar.css";

import clsx from "clsx";
import type { CustomComponentProps } from "~/components";
import type {
  GooeyBuilderData,
  NavAccountData,
  NavigationSidebarProps,
} from "@gooey-types/navigation_sidebar_props";
import type { Placement } from "tippy.js";
import { useState, useEffect, useRef } from "react";
import { PrimaryNavItems } from "./PrimaryNavItems";
import { WorkspaceAccountMenu } from "./WorkspaceAccountMenu";

const NAV_COLLAPSED_KEY = "nav-sidebar:default-collapsed";
// Keep in sync with SWITCH_WORKSPACE_KEY in workspaces/widgets.py
const SWITCH_WORKSPACE_KEY = "--switch-workspace";
// Matches the Sidebar `name`/`key` used for the Builder panel (sidebar_layout
// in widgets/sidebar.py). Sidebar.tsx persists its open state under this key,
// so the rail can read it to stay in sync across page navigations.
const BUILDER_SIDEBAR_KEY = "builder-sidebar";
// Below this width the rail becomes an off-canvas drawer (matches the CSS
// breakpoint in NavigationSidebar.css).
const MOBILE_MEDIA_QUERY = "(max-width: 991.98px)";

function isMobileViewport() {
  if (typeof window === "undefined") return false;
  return window.matchMedia(MOBILE_MEDIA_QUERY).matches;
}

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
        <GooeyBuilderButton gooey_builder={gooey_builder} compact={railCollapsed} />
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

function NavigationHeaderMobile({
  logo_image_url,
  isMobile,
  drawerOpen,
  onDrawerOpen,
  onDrawerClose,
  gooey_builder,
  builderOpen,
  account,
  onSwitchWorkspace,
}: {
  logo_image_url: NavigationSidebarProps["logo_image_url"];
  isMobile: boolean;
  drawerOpen: boolean;
  onDrawerOpen: () => void;
  onDrawerClose: () => void;
  gooey_builder: NavigationSidebarProps["gooey_builder"];
  builderOpen: boolean;
  account: NavAccountData;
  onSwitchWorkspace: (workspaceId: number) => void;
}) {
  return (
    <>
      <div className="nav-mobile-topbar d-lg-none d-flex align-items-center gap-2 px-2 border-bottom bg-body">
        <button
          type="button"
          className="btn text-muted p-2 d-flex align-items-center"
          title="Open menu"
          onClick={onDrawerOpen}
        >
          <i className="fa-regular fa-sidebar"></i>
        </button>
        <a
          href="/"
          className="d-flex align-items-center gap-2 text-body text-decoration-none"
        >
          <GooeyBot size={22} />
          <img
            src={logo_image_url}
            alt="Gooey.AI"
            height={20}
            width={100}
            className="img-fluid"
          />
        </a>
        <div className="ms-auto d-flex align-items-center gap-1">
          {gooey_builder && !builderOpen && (
            <GooeyBuilderButton gooey_builder={gooey_builder} compact />
          )}
          <AccountSection
            account={account}
            onSwitchWorkspace={onSwitchWorkspace}
            compact
            placement="bottom-end"
          />
        </div>
      </div>

      {isMobile && drawerOpen && (
        <div className="nav-scrim" onClick={onDrawerClose} />
      )}
    </>
  );
}

function AccountSection({
  account,
  onSwitchWorkspace,
  compact,
  placement,
}: {
  account: NavAccountData;
  onSwitchWorkspace: (workspaceId: number) => void;
  compact: boolean;
  placement: Placement;
}) {
  if (account.user) {
    return (
      <WorkspaceAccountMenu
        account={account}
        onSwitchWorkspace={onSwitchWorkspace}
        compact={compact}
        placement={placement}
      />
    );
  }

  return (
    <a
      href={account.login_href}
      className={clsx(
        "d-flex align-items-center text-body text-decoration-none rounded p-2 bg-hover-light position-relative",
        compact ? "justify-content-center" : "w-100 gap-2"
      )}
      title={compact ? "Sign In" : undefined}
    >
      <i className="fa-regular fa-right-to-bracket nav-item-icon" />
      {!compact && <span className="fw-semibold">Sign In</span>}
    </a>
  );
}

function GooeyBuilderButton({
  gooey_builder,
  compact,
}: {
  gooey_builder: GooeyBuilderData;
  compact: boolean;
}) {
  return (
    <button
      type="button"
      className={clsx(
        "gooey-builder-btn btn btn-light border d-flex align-items-center position-relative",
        compact ? "justify-content-center p-1" : "gap-2 p-2"
      )}
      title={"Gooey Builder"}
      onClick={(e) => {
        e.stopPropagation();
        window.dispatchEvent(new CustomEvent(`${BUILDER_SIDEBAR_KEY}:open`));
      }}
    >
      <img
        src={gooey_builder.photo_url}
        alt=""
        width={28}
        height={28}
        className="rounded-circle flex-shrink-0"
      />
      {!compact && (
        <span className="d-flex flex-column text-start lh-sm small">
          <span className="text-muted small">Build with AI</span>
          <span className="fw-semibold">Gooey Builder</span>
        </span>
      )}
    </button>
  );
}

function NavigationHeader({
  logo_image_url,
  railCollapsed,
  isMobile,
  onExpand,
  onCollapse,
  onDrawerClose,
}: {
  logo_image_url: NavigationSidebarProps["logo_image_url"];
  railCollapsed: boolean;
  isMobile: boolean;
  onExpand: (e?: React.MouseEvent) => void;
  onCollapse: () => void;
  onDrawerClose: () => void;
}) {
  return (
    <div className="nav-sidebar-header d-flex align-items-center p-2 mb-1 flex-shrink-0">
      <NavBrand
        logo_image_url={logo_image_url}
        collapsed={railCollapsed}
        onExpand={onExpand}
      />

      {!railCollapsed &&
        (isMobile ? (
          <button
            type="button"
            className="btn text-body p-1 d-flex align-items-center"
            title="Close menu"
            onClick={onDrawerClose}
          >
            <i className="fa-regular fa-xmark fa-lg" />
          </button>
        ) : (
          <button
            type="button"
            className="btn text-muted p-1 d-flex align-items-center bg-hover-light"
            title="Collapse sidebar"
            onClick={onCollapse}
          >
            <i className="fa-regular fa-sidebar"></i>
          </button>
        ))}
    </div>
  );
}

function NavBrand({
  logo_image_url,
  collapsed,
  onExpand,
}: {
  logo_image_url: NavigationSidebarProps["logo_image_url"];
  collapsed: boolean;
  onExpand?: (e?: React.MouseEvent) => void;
}) {
  const mark = (
    <span className="position-relative" aria-hidden="true">
      <GooeyBot size={24} />
      {collapsed && (
        <i className="fa-regular fa-sidebar nav-brand__expand-icon fs-5 text-muted" />
      )}
    </span>
  );

  if (collapsed) {
    return (
      <button
        type="button"
        className="nav-brand nav-brand--collapsed nav-item-link btn border-0 d-flex align-items-center justify-content-center p-2 rounded"
        aria-label="Expand sidebar"
        onClick={onExpand}
      >
        {mark}
      </button>
    );
  }

  return (
    <a
      href="/"
      className="nav-brand d-flex align-items-center gap-2 text-body text-decoration-none"
    >
      {mark}
      <img
        src={logo_image_url}
        alt="Gooey.AI"
        height={22}
        width={120}
        className="nav-brand__wordmark img-fluid"
      />
    </a>
  );
}

function GooeyBot({ size = 18 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={(size * 210) / 278}
      viewBox="0 0 278 210"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className="gooey-bot-icon"
    >
      <path
        fill="currentColor"
        d="M218.096 86.7852C223.618 86.7852 228.096 91.2625 228.096 96.7852V199.808C228.095 205.33 223.618 209.808 218.096 209.808H59.3584C53.8359 209.807 49.3586 205.33 49.3584 199.808V96.7852C49.3586 91.2626 53.8359 86.7854 59.3584 86.7852H218.096ZM38.5146 186.147H9C4.02955 186.147 0 182.118 0 177.147V120.858C0.000164041 115.888 4.02965 111.859 9 111.858H38.5146V186.147ZM268.455 111.858C273.426 111.858 277.455 115.888 277.455 120.858V177.147C277.455 182.118 273.426 186.147 268.455 186.147H238.94V111.858H268.455ZM92.457 130.898C82.7529 130.899 74.8859 138.766 74.8857 148.47C74.8857 158.174 82.7528 166.042 92.457 166.042C102.162 166.042 110.029 158.174 110.029 148.47C110.029 138.765 102.162 130.898 92.457 130.898ZM184.998 130.898C175.294 130.899 167.426 138.765 167.426 148.47C167.426 158.174 175.294 166.042 184.998 166.042C194.703 166.042 202.569 158.174 202.569 148.47C202.569 138.765 194.702 130.899 184.998 130.898ZM138.729 0C146.761 0.00018554 153.273 6.5121 153.273 14.5449C153.273 20.1275 150.128 24.9748 145.513 27.4131V81.5713H131.942V27.4121C127.328 24.9736 124.183 20.127 124.183 14.5449C124.183 6.51199 130.696 0 138.729 0Z"
      />
    </svg>
  );
}

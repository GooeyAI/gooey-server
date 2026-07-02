import "./NavigationSidebar.css";

import clsx from "clsx";
import type { CustomComponentProps } from "~/components";
import type {
  GooeyBuilderData,
  NavAccountData,
  NavigationSidebarProps,
} from "@gooey-types/navigation_sidebar_props";
import type { Placement } from "tippy.js";
import { useState, useEffect, useRef, Fragment } from "react";
import { GoogleSignInButton } from "./GoogleSignInButton";
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
    <div className="nav-mobile-topbar-container d-block d-lg-none">
      <div className="nav-mobile-topbar d-lg-none d-flex align-items-center gap-2 px-2 border-bottom bg-body">
        <button
          type="button"
          className="btn p-2 d-flex align-items-center m-0"
          title="Open menu"
          onClick={onDrawerOpen}
        >
          <i className="fa-regular fa-sidebar fs-5"></i>
        </button>
        <a
          href="/"
          className="d-flex align-items-center gap-2 text-body text-decoration-none bg-hover-light"
        >
          <GooeyBot size={24} />
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
            mobile
          />
        </div>
      </div>

      {isMobile && drawerOpen && (
        <div className="nav-scrim" onClick={onDrawerClose} />
      )}
    </div>
  );
}

function AccountSection({
  account,
  onSwitchWorkspace,
  compact,
  placement,
  mobile = false,
}: {
  account: NavAccountData;
  onSwitchWorkspace: (workspaceId: number) => void;
  compact: boolean;
  placement: Placement;
  mobile?: boolean;
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
    <SignedOutAccount account={account} compact={compact} mobile={mobile} />
  );
}

function SignedOutAccount({
  account,
  compact,
  mobile,
}: {
  account: NavAccountData;
  compact: boolean;
  mobile: boolean;
}) {
  // Mobile top bar (horizontal): always keep the "Sign In" text, and show the
  // Google icon button beside it when Firebase auth is on.
  if (mobile) {
    return (
      <div className="d-flex align-items-center gap-1">
        <SignInLink href={account.login_href} />
        {account.enable_firebase_auth && <GoogleSignInButton compact />}
      </div>
    );
  }

  // Collapsed rail (narrow, vertical): room for a single icon-sized affordance.
  if (compact) {
    if (account.enable_firebase_auth) return <GoogleSignInButton compact />;
    return <SignInLink href={account.login_href} iconOnly />;
  }

  // Expanded rail: full Google button + subtle "Sign In" link (or just the link
  // when Firebase auth is off).
  if (account.enable_firebase_auth) {
    return (
      <div className="d-flex flex-column align-items-stretch gap-1">
        <GoogleSignInButton compact={false} />
        <SignInLink href={account.login_href} subtle block />
      </div>
    );
  }
  return <SignInLink href={account.login_href} block />;
}

function SignInLink({
  href,
  iconOnly = false,
  subtle = false,
  block = false,
}: {
  href: string;
  iconOnly?: boolean;
  subtle?: boolean;
  block?: boolean;
}) {
  return (
    <a
      href={href}
      className={clsx(
        "d-flex align-items-center justify-content-center text-decoration-none rounded p-2 bg-hover-light position-relative",
        !iconOnly && "gap-2",
        block && "w-100",
        subtle ? "small" : "text-body"
      )}
      title={iconOnly ? "Sign In" : undefined}
    >
      {iconOnly ? (
        <i className="fa-regular fa-arrow-right-to-bracket" />
      ) : (
        <span className={clsx(!subtle && "fw-semibold")}>Sign In</span>
      )}
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
        "gooey-builder-btn btn border b-1 bg-hover-light d-flex align-items-center position-relative",
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
            className="btn text-body p-1 d-flex align-items-center bg-hover-light"
            title="Close menu"
            onClick={onDrawerClose}
          >
            <i className="fa-regular fa-xmark" />
          </button>
        ) : (
          <button
            type="button"
            className="btn text-muted p-1 d-flex align-items-center bg-hover-light"
            title="Collapse sidebar"
            onClick={onCollapse}
          >
            <i className="fa-regular fa-sidebar fs-5"></i>
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
    <Fragment>
      <GooeyBot size={24} className="gooey-bot-icon" />
      {collapsed && (
        <i className="fa-regular fa-sidebar nav-brand__expand-icon fs-5" />
      )}
    </Fragment>
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

function GooeyBot({
  size = 18,
  className,
}: {
  size?: number;
  className?: string;
}) {
  // The artwork fills its 133×100 viewBox edge-to-edge, so the rendered box must
  // keep that 133:100 ratio or it letterboxes (empty margin above/below the mark).
  // `size` is the width; height follows the aspect ratio.
  return (
    <svg
      width={size}
      height={(size * 100) / 133}
      style={{ transform: "translateY(-1px)" }}
      viewBox="0 0 133 100"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
    >
      <path
        d="M103.951 41.3643C106.583 41.3645 108.717 43.4988 108.717 46.1309V95.2334C108.717 97.8656 106.583 99.9998 103.951 100H28.292C25.6599 99.9997 23.5254 97.8656 23.5254 95.2334V46.1309C23.5256 43.4988 25.66 41.3645 28.292 41.3643H103.951ZM18.3574 88.7236H8.5791C3.84111 88.7234 0.00012829 84.8825 0 80.1445V61.8945C1.56959e-05 57.1564 3.84104 53.3156 8.5791 53.3154H18.3574V88.7236ZM123.664 53.3154C128.402 53.3155 132.243 57.1564 132.243 61.8945V80.1445C132.243 84.8826 128.402 88.7235 123.664 88.7236H113.886V53.3154H123.664ZM44.0674 62.3896C39.4424 62.3901 35.6926 66.1396 35.6924 70.7646C35.6924 75.3899 39.4422 79.1392 44.0674 79.1396C48.6929 79.1396 52.4434 75.3902 52.4434 70.7646C52.4431 66.1393 48.6927 62.3896 44.0674 62.3896ZM88.1748 62.3896C83.5498 62.3901 79.8 66.1396 79.7998 70.7646C79.7998 75.3899 83.5497 79.1392 88.1748 79.1396C92.8003 79.1396 96.5508 75.3902 96.5508 70.7646C96.5505 66.1393 92.8002 62.3896 88.1748 62.3896ZM66.1221 0C69.9508 8.06595e-05 73.0547 3.10389 73.0547 6.93262C73.0547 9.59326 71.5549 11.9022 69.3555 13.0645V38.8799H62.8877V13.0635C60.6888 11.9011 59.1895 9.59289 59.1895 6.93262C59.1895 3.10384 62.2933 0 66.1221 0Z"
        fill="black"
      />
    </svg>
  );
}

import "./NavigationSidebar.css";

import clsx from "clsx";
import type { CustomComponentProps } from "~/components";
import type { NavigationSidebarProps } from "@gooey-types/navigation_sidebar_props";
import { useState, useEffect, useRef } from "react";
import { IdentityMenu } from "./IdentityMenu";
import { PrimaryNavItems } from "./PrimaryNavItems";

const NAV_COLLAPSED_KEY = "nav-sidebar:default-collapsed";

export function NavigationSidebar({
  logo_image_url,
  nav_items,
  active_key,
  new_href,
  default_collapsed,
  saved_workflows,
  recent_workflows,
  user,
  current_workspace,
  workspaces,
  menu_links,
  logout_href,
  switch_workspace_href,
  add_workspace_href,
  login_href,
  gooey_builder,
  onChange,
  state,
}: CustomComponentProps & NavigationSidebarProps) {
  const [collapsed, setCollapsed] = useState(default_collapsed);
  const [isMobile, setIsMobile] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [builderOpen, setBuilderOpen] = useState(false);
  const [builderCollapsedRail, setBuilderCollapsedRail] = useState(false);
  const mounted = useRef(false);

  useEffect(() => {
    if (!mounted.current) {
      mounted.current = true;
      if (state[NAV_COLLAPSED_KEY] === collapsed) return;
    }
    state[NAV_COLLAPSED_KEY] = collapsed;
    onChange();
  }, [collapsed]);

  useEffect(() => {
    const mq = window.matchMedia("(max-width: 991.98px)");
    const update = () => setIsMobile(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    const onOpen = () => {
      setBuilderOpen(true);
      setBuilderCollapsedRail(true);
      setDrawerOpen(false);
    };
    const onClose = () => {
      setBuilderOpen(false);
      setBuilderCollapsedRail(false);
    };
    window.addEventListener("builder-sidebar:open", onOpen);
    window.addEventListener("builder-sidebar:close", onClose);
    return () => {
      window.removeEventListener("builder-sidebar:open", onOpen);
      window.removeEventListener("builder-sidebar:close", onClose);
    };
  }, []);

  const railCollapsed = !isMobile && (collapsed || builderCollapsedRail);

  const expandRail = (e?: React.MouseEvent) => {
    e?.preventDefault();
    setBuilderCollapsedRail(false);
    setCollapsed(false);
  };

  const navClass = clsx(
    "nav-sidebar d-flex flex-column p-2 border-end bg-body",
    railCollapsed && "nav-sidebar--collapsed",
    isMobile && drawerOpen && "nav-sidebar--drawer-open"
  );

  return (
    <div>
      <NavigationHeaderMobile
        logoImageUrl={logo_image_url}
        isMobile={isMobile}
        drawerOpen={drawerOpen}
        onDrawerOpen={() => setDrawerOpen(true)}
        onDrawerClose={() => setDrawerOpen(false)}
      />

      <nav
        className={navClass}
        onClick={railCollapsed ? () => expandRail() : undefined}
      >
        <NavigationHeader
          logoImageUrl={logo_image_url}
          railCollapsed={railCollapsed}
          isMobile={isMobile}
          onExpand={expandRail}
          onCollapse={() => setCollapsed(true)}
          onDrawerClose={() => setDrawerOpen(false)}
        />

        <PrimaryNavItems
          navItems={nav_items}
          activeKey={active_key}
          newHref={new_href}
          savedWorkflows={saved_workflows}
          recentWorkflows={recent_workflows}
          user={user}
          menuLinks={menu_links}
          railCollapsed={railCollapsed}
        />

        <NavigationFooter
          gooeyBuilder={gooey_builder}
          railCollapsed={railCollapsed}
          builderOpen={builderOpen}
          user={user}
          currentWorkspace={current_workspace}
          workspaces={workspaces}
          menuLinks={menu_links}
          logoutHref={logout_href}
          switchWorkspaceHref={switch_workspace_href}
          addWorkspaceHref={add_workspace_href}
          loginHref={login_href}
        />
      </nav>
    </div>
  );
}

function NavigationFooter({
  gooeyBuilder,
  railCollapsed,
  builderOpen,
  user,
  currentWorkspace,
  workspaces,
  menuLinks,
  logoutHref,
  switchWorkspaceHref,
  addWorkspaceHref,
  loginHref,
}: {
  gooeyBuilder: NavigationSidebarProps["gooey_builder"];
  railCollapsed: boolean;
  builderOpen: boolean;
  user: NavigationSidebarProps["user"];
  currentWorkspace: NavigationSidebarProps["current_workspace"];
  workspaces: NavigationSidebarProps["workspaces"];
  menuLinks: NavigationSidebarProps["menu_links"];
  logoutHref: string;
  switchWorkspaceHref: string;
  addWorkspaceHref: string;
  loginHref: string;
}) {
  return (
    <div className="flex-shrink-0 pt-2 d-flex flex-column gap-2">
      {gooeyBuilder && !(railCollapsed && builderOpen) && (
        <button
          type="button"
          className={clsx(
            "gooey-builder-btn btn btn-light border d-flex align-items-center position-relative",
            railCollapsed ? "justify-content-center p-1" : "gap-2 p-2"
          )}
          title={railCollapsed ? "Gooey Builder" : undefined}
          onClick={(e) => {
            e.stopPropagation();
            window.dispatchEvent(new CustomEvent("builder-sidebar:open"));
          }}
        >
          <img
            src={gooeyBuilder.photo_url}
            alt=""
            width={28}
            height={28}
            className="gooey-builder-btn__photo rounded-circle flex-shrink-0"
          />
          {railCollapsed ? (
            <RailTooltip label="Gooey Builder" />
          ) : (
            <span className="d-flex flex-column text-start lh-sm">
              <span className="gooey-builder-btn__subtitle text-muted">
                Build with AI
              </span>
              <span className="fw-semibold">Gooey Builder</span>
            </span>
          )}
        </button>
      )}

      {user ? (
        <IdentityMenu
          user={user}
          currentWorkspace={currentWorkspace ?? null}
          workspaces={workspaces}
          menuLinks={menuLinks}
          logoutHref={logoutHref}
          switchWorkspaceHref={switchWorkspaceHref}
          addWorkspaceHref={addWorkspaceHref}
          collapsed={railCollapsed}
        />
      ) : (
        <a
          href={loginHref}
          className={clsx(
            "d-flex align-items-center w-100 text-body text-decoration-none rounded p-2 bg-hover-light position-relative",
            railCollapsed ? "justify-content-center" : "gap-2"
          )}
          title={railCollapsed ? "Sign In" : undefined}
        >
          <i className="fa-regular fa-right-to-bracket nav-item-icon" />
          {railCollapsed ? (
            <RailTooltip label="Sign In" />
          ) : (
            <span className="fw-semibold">Sign In</span>
          )}
        </a>
      )}
    </div>
  );
}

function NavigationHeaderMobile({
  logoImageUrl,
  isMobile,
  drawerOpen,
  onDrawerOpen,
  onDrawerClose,
}: {
  logoImageUrl: string;
  isMobile: boolean;
  drawerOpen: boolean;
  onDrawerOpen: () => void;
  onDrawerClose: () => void;
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
            src={logoImageUrl}
            alt="Gooey.AI"
            height={20}
            width={100}
            className="img-fluid"
          />
        </a>
      </div>

      {isMobile && drawerOpen && (
        <div className="nav-scrim" onClick={onDrawerClose} />
      )}
    </>
  );
}

function NavigationHeader({
  logoImageUrl,
  railCollapsed,
  isMobile,
  onExpand,
  onCollapse,
  onDrawerClose,
}: {
  logoImageUrl: string;
  railCollapsed: boolean;
  isMobile: boolean;
  onExpand: (e?: React.MouseEvent) => void;
  onCollapse: () => void;
  onDrawerClose: () => void;
}) {
  return (
    <div className="nav-sidebar-header d-flex align-items-center p-2 mb-1 flex-shrink-0">
      <NavBrand
        logoImageUrl={logoImageUrl}
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
            className="btn text-muted p-1 d-flex align-items-center"
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
  logoImageUrl,
  collapsed,
  onExpand,
}: {
  logoImageUrl: string;
  collapsed: boolean;
  onExpand?: (e?: React.MouseEvent) => void;
}) {
  const mark = (
    <span className="nav-brand__mark" aria-hidden="true">
      <GooeyBot size={24} />
      {collapsed && (
        <i className="fa-regular fa-sidebar nav-brand__expand-icon " />
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
        src={logoImageUrl}
        alt="Gooey.AI"
        height={22}
        width={120}
        className="nav-brand__wordmark img-fluid"
      />
    </a>
  );
}

function RailTooltip({ label }: { label: string }) {
  return <span className="rail-tooltip">{label}</span>;
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

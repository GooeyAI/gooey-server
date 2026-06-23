import "./NavigationSidebar.css";

import type { CustomComponentProps } from "~/components";
import type { NavigationSidebarProps } from "@gooey-types/navigation_sidebar_props";
import { useState, useEffect, useRef } from "react";
import { WorkflowList } from "./WorkflowList";

const NAV_COLLAPSED_KEY = "nav-sidebar:default-collapsed";

function GooeyBot({ size = 18 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={(size * 210) / 278}
      viewBox="0 0 278 210"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      style={{ display: "block" }}
    >
      <path
        fill="currentColor"
        d="M218.096 86.7852C223.618 86.7852 228.096 91.2625 228.096 96.7852V199.808C228.095 205.33 223.618 209.808 218.096 209.808H59.3584C53.8359 209.807 49.3586 205.33 49.3584 199.808V96.7852C49.3586 91.2626 53.8359 86.7854 59.3584 86.7852H218.096ZM38.5146 186.147H9C4.02955 186.147 0 182.118 0 177.147V120.858C0.000164041 115.888 4.02965 111.859 9 111.858H38.5146V186.147ZM268.455 111.858C273.426 111.858 277.455 115.888 277.455 120.858V177.147C277.455 182.118 273.426 186.147 268.455 186.147H238.94V111.858H268.455ZM92.457 130.898C82.7529 130.899 74.8859 138.766 74.8857 148.47C74.8857 158.174 82.7528 166.042 92.457 166.042C102.162 166.042 110.029 158.174 110.029 148.47C110.029 138.765 102.162 130.898 92.457 130.898ZM184.998 130.898C175.294 130.899 167.426 138.765 167.426 148.47C167.426 158.174 175.294 166.042 184.998 166.042C194.703 166.042 202.569 158.174 202.569 148.47C202.569 138.765 194.702 130.899 184.998 130.898ZM138.729 0C146.761 0.00018554 153.273 6.5121 153.273 14.5449C153.273 20.1275 150.128 24.9748 145.513 27.4131V81.5713H131.942V27.4121C127.328 24.9736 124.183 20.127 124.183 14.5449C124.183 6.51199 130.696 0 138.729 0Z"
      />
    </svg>
  );
}

/** Dark tooltip that appears to the right of a collapsed rail item on hover. */
function RailTooltip({ label }: { label: string }) {
  return <span className="rail-tooltip">{label}</span>;
}

/** A single nav item row — handles both expanded and collapsed rendering. */
function NavItem({
  icon,
  label,
  href,
  isActive,
  collapsed,
}: {
  icon: string;
  label: string;
  href: string;
  isActive: boolean;
  collapsed: boolean;
}) {
  const baseClass = [
    "nav-item-link d-flex align-items-center gap-2 rounded text-decoration-none",
    collapsed ? "justify-content-center px-0 py-2" : "px-2 py-2",
    isActive ? "fw-bold bg-body-secondary text-body" : "text-body",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <a href={href} className={baseClass + (collapsed ? " position-relative" : "")}>
      <i className={icon} style={{ width: 18, textAlign: "center", flexShrink: 0 }} />
      {collapsed ? (
        <RailTooltip label={label} />
      ) : (
        <span>{label}</span>
      )}
    </a>
  );
}

export function NavigationSidebar({
  logo_image_url,
  nav_items,
  active_key,
  new_href,
  default_collapsed,
  saved_workflows,
  recent_workflows,
  saved_href,
  onChange,
  state,
}: CustomComponentProps & NavigationSidebarProps) {
  const [collapsed, setCollapsed] = useState(default_collapsed);
  const [savedOpen, setSavedOpen] = useState(true);
  const [recentOpen, setRecentOpen] = useState(true);
  // Track whether we should skip the first effect run (no-op on mount if value unchanged).
  const mounted = useRef(false);

  // Mirror the Sidebar.tsx pattern: when collapsed changes, persist via state + onChange().
  useEffect(() => {
    if (!mounted.current) {
      mounted.current = true;
      // Only post on mount if the value differs from what the server sent.
      if (state[NAV_COLLAPSED_KEY] === collapsed) return;
    }
    state[NAV_COLLAPSED_KEY] = collapsed;
    onChange();
  }, [collapsed]);

  const navClass = [
    "nav-sidebar d-flex flex-column p-2 border-end bg-body",
    collapsed ? "nav-sidebar--collapsed" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <nav
      className={navClass}
      onClick={
        collapsed
          ? (e) => {
              // Expand when clicking the rail background (not a child link/button).
              if (e.currentTarget === e.target) setCollapsed(false);
            }
          : undefined
      }
    >
      {/* Header: logo + wordmark + collapse toggle */}
      <div
        className="d-flex align-items-center p-2 mb-1"
        style={{ height: 56, gap: collapsed ? 0 : 8, justifyContent: collapsed ? "center" : "space-between" }}
      >
        <a
          href="/"
          className="d-flex align-items-center gap-2 text-body text-decoration-none"
          style={{ minWidth: 0, overflow: "hidden" }}
        >
          <GooeyBot size={24} />
          {!collapsed && (
            <img
              src={logo_image_url}
              alt="Gooey.AI"
              height={22}
              className="img-fluid"
              style={{ flexShrink: 0 }}
            />
          )}
        </a>

        {!collapsed && (
          <button
            className="btn btn-link text-body p-1 d-flex align-items-center"
            style={{ lineHeight: 1 }}
            title="Collapse sidebar"
            onClick={() => setCollapsed(true)}
          >
            <i className="fa-regular fa-sidebar" />
          </button>
        )}

        {collapsed && (
          <button
            className="btn btn-link text-body p-0 d-flex align-items-center position-relative"
            style={{ lineHeight: 1, marginLeft: 0 }}
            title="Expand sidebar"
            onClick={() => setCollapsed(false)}
          >
            <RailTooltip label="Expand" />
          </button>
        )}
      </div>

      {/* Sticky "New" button */}
      <a
        href={new_href}
        className={[
          "btn btn-primary d-flex align-items-center mb-2 fw-semibold",
          collapsed ? "justify-content-center px-0" : "gap-2",
        ].join(" ")}
        title={collapsed ? "New" : undefined}
        style={{ position: "relative" }}
      >
        <i className="fa-regular fa-plus" />
        {collapsed ? <RailTooltip label="New" /> : <span>New</span>}
      </a>

      {/* Primary nav items */}
      <div className="d-flex flex-column gap-1">
        {nav_items.map((item) => (
          <NavItem
            key={item.key}
            icon={item.icon}
            label={item.label}
            href={item.href}
            isActive={item.key === active_key}
            collapsed={collapsed}
          />
        ))}

        {/* When collapsed, Recent appears as a single clock item */}
        {collapsed && (
          <NavItem
            key="recent-collapsed"
            icon="fa-regular fa-clock-rotate-left"
            label="Recent"
            href="#"
            isActive={false}
            collapsed={collapsed}
          />
        )}
      </div>

      {/* Saved tree — only when expanded and there are saved workflows */}
      {!collapsed && saved_workflows.length > 0 && (
        <div className="mt-2">
          <button
            className="btn btn-link text-body text-decoration-none d-flex align-items-center gap-1 px-2 py-1 w-100"
            style={{ fontSize: "0.75rem", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}
            onClick={() => setSavedOpen((v) => !v)}
          >
            <span className="flex-grow-1 text-start">Saved</span>
            <i className={`fa-regular fa-chevron-${savedOpen ? "down" : "right"}`} style={{ fontSize: 11 }} />
          </button>
          {savedOpen && (
            <div className="saved-tree">
              <WorkflowList items={saved_workflows} indent />
              {saved_href && (
                <a
                  href={saved_href}
                  className="d-block text-body-secondary text-decoration-none px-2 py-1"
                  style={{ fontSize: "0.8rem" }}
                >
                  View all
                </a>
              )}
            </div>
          )}
        </div>
      )}

      {/* Recent list — only when expanded and there are recent workflows */}
      {!collapsed && recent_workflows.length > 0 && (
        <div className="mt-2">
          <button
            className="btn btn-link text-body text-decoration-none d-flex align-items-center gap-1 px-2 py-1 w-100"
            style={{ fontSize: "0.75rem", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}
            onClick={() => setRecentOpen((v) => !v)}
          >
            <span className="flex-grow-1 text-start">Recent</span>
            <i className={`fa-regular fa-chevron-${recentOpen ? "down" : "right"}`} style={{ fontSize: 11 }} />
          </button>
          {recentOpen && <WorkflowList items={recent_workflows} />}
        </div>
      )}
    </nav>
  );
}

import clsx from "clsx";
import { useState } from "react";
import type {
  MenuLinkData,
  NavItemData,
  NavUserData,
  NavWorkflowData,
} from "@gooey-types/navigation_sidebar_props";
import { WorkflowList } from "./WorkflowList";

export function PrimaryNavItems({
  navItems,
  activeKey,
  newHref,
  savedWorkflows,
  recentWorkflows,
  user,
  menuLinks,
  railCollapsed,
}: {
  navItems: NavItemData[];
  activeKey: string | null | undefined;
  newHref: string;
  savedWorkflows: NavWorkflowData[];
  recentWorkflows: NavWorkflowData[];
  user: NavUserData | null | undefined;
  menuLinks: MenuLinkData[];
  railCollapsed: boolean;
}) {
  const [savedOpen, setSavedOpen] = useState(true);
  const [recentOpen, setRecentOpen] = useState(true);

  return (
    <>
      {user && (
        <div className="flex-shrink-0">
          <NavItem
            icon="fa-regular fa-plus"
            label="New"
            href={newHref}
            isActive={false}
            collapsed={railCollapsed}
          />
        </div>
      )}

      <div className="nav-scroll-region d-flex flex-column gap-1 mt-1">
        {navItems.map((item) => {
          if (item.key === "saved" && !railCollapsed && user) {
            return (
              <div key={item.key}>
                <div
                  className={clsx(
                    "nav-item-link d-flex align-items-center gap-2 rounded px-2 py-2",
                    item.key === activeKey
                      ? "fw-bold nav-item-link--active text-body"
                      : "text-body",
                  )}
                >
                  <a
                    href={item.href}
                    className="nav-item-inner-link d-flex align-items-center gap-2 flex-grow-1 text-reset text-decoration-none"
                  >
                    <i className={clsx(item.icon, "nav-item-icon")} />
                    <span>{item.label}</span>
                  </a>
                  {savedWorkflows.length > 0 && (
                    <button
                      type="button"
                      className="nav-chevron-btn btn text-body p-0 d-flex align-items-center"
                      title={savedOpen ? "Collapse" : "Expand"}
                      onClick={() => setSavedOpen((v) => !v)}
                    >
                      <i
                        className={clsx(
                          "nav-chevron-icon fa-regular",
                          savedOpen ? "fa-chevron-down" : "fa-chevron-right",
                        )}
                      />
                    </button>
                  )}
                </div>
                {savedOpen && savedWorkflows.length > 0 && (
                  <div className="saved-tree">
                    <WorkflowList items={savedWorkflows} indent />
                  </div>
                )}
              </div>
            );
          }
          return (
            <NavItem
              key={item.key}
              icon={item.icon}
              label={item.label}
              href={item.href}
              isActive={item.key === activeKey}
              collapsed={railCollapsed}
            />
          );
        })}

        {railCollapsed && user && (
          <NavItem
            key="recent-collapsed"
            icon="fa-regular fa-clock-rotate-left"
            label="Recent"
            href="#"
            isActive={false}
            collapsed={railCollapsed}
          />
        )}

        {!user &&
          !railCollapsed &&
          menuLinks.map((link, i) => (
            <a
              key={i}
              href={link.href}
              className="nav-item-link d-flex align-items-center gap-2 rounded text-decoration-none px-2 py-2 text-body"
            >
              {link.icon && (
                <i className={clsx(link.icon, "nav-item-icon")} />
              )}
              <span>{link.label}</span>
            </a>
          ))}

        {!railCollapsed && recentWorkflows.length > 0 && (
          <div className="mt-3">
            <button
              className="nav-section-toggle btn text-body text-decoration-none d-flex align-items-center gap-1 px-2 py-1 w-100"
              onClick={() => setRecentOpen((v) => !v)}
            >
              <span className="flex-grow-1 text-start">Recent</span>
              <i
                className={clsx(
                  "fa-regular",
                  recentOpen ? "fa-chevron-down" : "fa-chevron-right",
                )}
              />
            </button>
            {recentOpen && <WorkflowList items={recentWorkflows} />}
          </div>
        )}
      </div>
    </>
  );
}

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
  return (
    <a
      href={href}
      className={clsx(
        "nav-item-link d-flex align-items-center gap-2 rounded text-decoration-none",
        collapsed ? "justify-content-center px-0 py-2" : "px-2 py-2",
        isActive ? "fw-bold nav-item-link--active text-body" : "text-body",
        collapsed && "position-relative",
      )}
      onClick={collapsed ? (e) => e.preventDefault() : undefined}
    >
      <i className={clsx(icon, "nav-item-icon")} />
      {collapsed ? <RailTooltip label={label} /> : <span>{label}</span>}
    </a>
  );
}

function RailTooltip({ label }: { label: string }) {
  return <span className="rail-tooltip">{label}</span>;
}

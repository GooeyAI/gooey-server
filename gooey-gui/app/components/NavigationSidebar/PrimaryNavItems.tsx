import clsx from "clsx";
import React, { useState } from "react";
import type {
  MenuLinkData,
  NavItemData,
  NavUserData,
  NavWorkflowItem,
} from "@gooey-types/navigation_sidebar_props";
import { WorkflowList } from "./WorkflowList";

export function PrimaryNavItems({
  navItems,
  activeKey,
  recentWorkflows,
  user,
  menuLinks,
  railCollapsed,
}: {
  navItems: NavItemData[];
  activeKey: string | null | undefined;
  recentWorkflows: NavWorkflowItem[];
  user: NavUserData | null | undefined;
  menuLinks: MenuLinkData[];
  railCollapsed: boolean;
}) {
  const [recentOpen, setRecentOpen] = useState(true);

  const home = navItems.filter((item) => item.key === "home")[0];
  return (
    <div className="px-2 pt-2 nav-primary-items d-flex flex-column">
      {home && (
        <NavItem
          icon={home.icon}
          label={home.label}
          href={home.href}
          isActive={home.key === activeKey}
          collapsed={railCollapsed}
        />
      )}

      {/* scrollable region */}
      <div className="nav-scroll-region d-flex flex-column gap-1 mt-1">
        {navItems.map((item) => {
          if (item.key === "home") return null;
          if (item.items.length > 0 && !railCollapsed) {
            return (
              <NavItemChildren
                key={item.key}
                icon={item.icon}
                label={item.label}
                href={item.href}
                isActive={item.key === activeKey}
                items={item.items}
              />
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

        {!user &&
          !railCollapsed &&
          menuLinks.map((link) => (
            <a
              key={`${link.href}:${link.label}`}
              href={link.href}
              className="nav-item-link d-flex align-items-center gap-2 rounded text-decoration-none px-2 py-2 text-body"
            >
              {link.icon && <i className={clsx(link.icon, "nav-item-icon")} />}
              <span>{link.label}</span>
            </a>
          ))}

        {!railCollapsed && recentWorkflows.length > 0 && (
          <div className="mt-3 pe-1 nav-section-toggle fs-6">
            <button
              type="button"
              className="nav-item-link d-flex align-items-center fw-semibold gap-1 px-1 py-1 w-100 rounded"
              onClick={() => setRecentOpen((v) => !v)}
            >
              <span className="text-start small text-muted">Recent</span>
              <i
                className={clsx(
                  "fa-regular text-muted nav-chevron-icon",
                  recentOpen ? "fa-chevron-down" : "fa-chevron-right"
                )}
              />
            </button>
            {recentOpen && <WorkflowList items={recentWorkflows} />}
          </div>
        )}
      </div>
    </div>
  );
}

function NavItem({
  icon,
  label,
  href,
  isActive,
  collapsed,
  children,
}: {
  icon: string;
  label: string;
  href: string;
  isActive: boolean;
  collapsed: boolean;
  children?: React.ReactNode;
}) {
  return (
    <a
      className={clsx(
        "nav-item-link d-flex align-items-center gap-2 rounded",
        collapsed ? "justify-content-center px-0 py-2" : "px-2 py-2",
        isActive ? "fw-bold nav-item-link--active text-body" : "text-body",
        collapsed && "position-relative",
        children && "nav-section-toggle"
      )}
      href={href}
      onClick={(e) => e.stopPropagation()} // avoid opening the sidebar
    >
      <span
        className={clsx(
          "d-flex align-items-center gap-2 flex-grow-1",
          collapsed && "justify-content-center"
        )}
      >
        <i className={clsx(icon, "nav-item-icon", !isActive && "text-muted")} />
        {!collapsed && <span>{label}</span>}
      </span>
      {children}
    </a>
  );
}

function NavItemChildren({
  icon,
  label,
  href,
  isActive,
  items,
}: {
  icon: string;
  label: string;
  href: string;
  isActive: boolean;
  items: NavWorkflowItem[];
}) {
  const [open, setOpen] = useState(true);

  // No children → behaves like a plain nav item (label links to href).
  if (items.length === 0) {
    return (
      <NavItem
        icon={icon}
        label={label}
        href={href}
        isActive={isActive}
        collapsed={false}
      />
    );
  }

  return (
    <React.Fragment>
      <NavItem
        icon={icon}
        label={label}
        href={href}
        isActive={isActive}
        collapsed={false}
      >
        {/* the space after the label toggles the nested items open/closed */}
        <span
          className="flex-grow-1 d-flex align-items-center justify-content-end flex-grow-1"
          onClick={(e) => {
            e.preventDefault();
            setOpen((isOpen) => !isOpen);
          }}
        >
          <i
            className={clsx(
              "nav-chevron-icon fa-regular",
              open ? "fa-chevron-down" : "fa-chevron-right"
            )}
          />
        </span>
      </NavItem>
      {open && (
        <div className="saved-tree">
          <WorkflowList items={items} indent />
        </div>
      )}
    </React.Fragment>
  );
}

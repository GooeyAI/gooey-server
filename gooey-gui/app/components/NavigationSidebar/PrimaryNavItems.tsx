import clsx from "clsx";
import { Fragment, type ReactNode, useState } from "react";
import type {
  NavAccountData,
  NavItemData,
  NavigationSidebarProps,
} from "@gooey-types/navigation_sidebar_props";
import { WorkflowList } from "./WorkflowList";

export function PrimaryNavItems({
  nav_items,
  active_key,
  account,
  railCollapsed,
}: {
  nav_items: NavItemData[];
  active_key: NavigationSidebarProps["active_key"];
  account: NavAccountData;
  railCollapsed: boolean;
}) {
  return (
    <div className="px-2 nav-primary-items d-flex flex-column">
      {/* scrollable region */}
      <div className="nav-scroll-region d-flex flex-column gap-1 mt-1">
        {nav_items.map((item) => {
          if (item.items.length > 0 && !railCollapsed) {
            return (
              <NavItemChildren
                key={item.key}
                item={item}
                isActive={item.key === active_key}
              />
            );
          }
          return (
            <NavItem
              key={item.key}
              item={item}
              isActive={item.key === active_key}
              collapsed={railCollapsed}
            />
          );
        })}

        {!account.user &&
          !railCollapsed &&
          account.menu_links.map((link) => (
            <a
              key={`${link.href}:${link.label}`}
              href={link.href}
              className="nav-item-link d-flex align-items-center gap-2 rounded text-decoration-none px-2 py-2 text-body"
            >
              {link.icon && <i className={clsx(link.icon, "nav-item-icon")} />}
              <span>{link.label}</span>
            </a>
          ))}
      </div>
    </div>
  );
}

function NavItem({
  item,
  isActive,
  collapsed,
  children,
}: {
  item: NavItemData;
  isActive: boolean;
  collapsed: boolean;
  children?: ReactNode;
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
      href={item.href}
      onClick={(e) => e.stopPropagation()} // avoid opening the sidebar
    >
      <span
        className={clsx(
          "d-flex align-items-center gap-2 flex-grow-1",
          collapsed && "justify-content-center"
        )}
      >
        <i
          className={clsx(
            item.icon,
            "nav-item-icon",
            !isActive && "text-muted"
          )}
        />
        {!collapsed && <span>{item.label}</span>}
      </span>
      {children}
    </a>
  );
}

function NavItemChildren({
  item,
  isActive,
}: {
  item: NavItemData;
  isActive: boolean;
}) {
  const [open, setOpen] = useState(true);

  // No children → behaves like a plain nav item (label links to href).
  if (item.items.length === 0) {
    return <NavItem item={item} isActive={isActive} collapsed={false} />;
  }

  // Non-collapsible sections (e.g. History) drop the chevron and stay expanded.
  const showItems = !item.collapsible || open;

  return (
    <Fragment>
      <NavItem item={item} isActive={isActive} collapsed={false}>
        {/* the chevron after the label toggles the nested items open/closed */}
        {item.collapsible && (
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
        )}
      </NavItem>
      {showItems && (
        <div className="saved-tree">
          <WorkflowList items={item.items} indent />
        </div>
      )}
    </Fragment>
  );
}

import { Link, useLocation } from "@remix-run/react";
import * as Sentry from "@sentry/remix";
import clsx from "clsx";
import { Fragment, type ReactNode, useEffect, useState } from "react";
import type {
  NavAccountData,
  NavItemData,
  NavigationSidebarProps,
  NavWorkflowItem,
} from "@gooey-types/navigation_sidebar_props";
import { fetchServerAPI } from "~/fetchServerAPI";
import { WorkflowList, WorkflowListSkeleton } from "./WorkflowList";

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
      <div className="nav-scroll-region d-flex flex-column gap-1 mt-1">
        {nav_items.map((item) => {
          const hasChildren = item.items.length > 0 || !!item.items_url;
          if (hasChildren && !railCollapsed) {
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
              dense={item.dense}
            />
          );
        })}

        {!account.user &&
          !railCollapsed &&
          account.menu_links.map((link) => {
            const key = `${link.href}:${link.label}`;
            const className =
              "nav-item-link d-flex align-items-center gap-2 rounded text-decoration-none px-2 py-2 text-body bg-hover-light";
            const content = (
              <Fragment>
                {link.icon && (
                  <i className={clsx(link.icon, "nav-item-icon")} />
                )}
                <span>{link.label}</span>
              </Fragment>
            );
            if (isExternalHref(link.href)) {
              return (
                <a key={key} href={link.href} className={className}>
                  {content}
                </a>
              );
            }
            return (
              <Link key={key} to={link.href} className={className}>
                {content}
              </Link>
            );
          })}
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
  dense: boolean;
}) {
  const className = clsx(
    "nav-item-link d-flex align-items-center rounded",
    collapsed && "justify-content-center px-0 py-2",
    isActive ? "fw-bold nav-item-link--active text-body" : "text-body",
    collapsed && "position-relative",
    children && "nav-section-toggle",
    !!item.href && "bg-hover-light",
    item.dense ? "dense px-2 py-1 small" : "px-2 py-1"
  );
  const content = (
    <Fragment>
      <span
        className={clsx(
          "d-flex align-items-center flex-grow-1 gap-1",
          collapsed && "justify-content-center",
          collapsed && !item.href && "d-none" // hide when no href and collapsed
        )}
      >
        <span
          className="nav-item-icon"
          dangerouslySetInnerHTML={{ __html: item.icon }}
        />
        {!collapsed && <span>{item.label}</span>}
      </span>
      {children}
    </Fragment>
  );
  const stopPropagation = (e: React.MouseEvent) => e.stopPropagation();

  if (!item.href) {
    return (
      <div className={className} onClick={stopPropagation}>
        {content}
      </div>
    );
  }

  return (
    <Link
      className={className}
      to={item.href}
      onClick={stopPropagation} // avoid opening the sidebar
    >
      {content}
    </Link>
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
  const { items, isFetching } = useNavItemChildren(item);
  const showSkeleton = isFetching && items.length === 0;

  if (items.length === 0 && !showSkeleton) {
    // A fetched section has no href of its own, so an empty result means there's
    // nothing to link to — drop the whole section instead of a dead label.
    if (item.items_url) return null;
    // No children → behaves like a plain nav item (label links to href).
    return (
      <NavItem
        item={item}
        isActive={isActive}
        collapsed={false}
        dense={item.dense}
      />
    );
  }

  // Non-collapsible sections (e.g. History) drop the chevron and stay expanded.
  const showItems = !item.collapsible || open;

  return (
    <Fragment>
      <NavItem
        item={item}
        isActive={isActive}
        collapsed={false}
        dense={item.dense}
      >
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
        <div className={clsx(!item.dense && "saved-tree mb-2")}>
          {showSkeleton ? (
            <WorkflowListSkeleton rows={3} indent={!item.dense} />
          ) : (
            <WorkflowList items={items} indent={!item.dense} />
          )}
        </div>
      )}
    </Fragment>
  );
}

// Sections with an `items_url` load their rows after the page has rendered, so a
// slow query (History) never holds up SSR.
//
// The list is refetched on mount and on every url change -- starting a run
// redirects to that run's url, which is our cue that a new row exists -- and the
// result is cached per tab. The cache is shown right away and replaced silently
// once the fetch lands, so only the very first load of a tab shows a skeleton.
function useNavItemChildren(item: NavItemData) {
  const itemsUrl = item.items_url;
  const cacheKey = `${item.key}:${item.items_cache_key || ""}`;
  const location = useLocation();
  const locationKey = `${location.pathname}${location.search}`;

  const [items, setItems] = useState<NavWorkflowItem[] | null>(null);
  const [isFetching, setIsFetching] = useState(false);

  useEffect(() => {
    if (!itemsUrl) return;
    let cancelled = false;
    const cached = readCachedItems(cacheKey);
    if (cached) setItems(cached);
    setIsFetching(true);
    fetchServerAPI<{ items: NavWorkflowItem[] }>(itemsUrl)
      .then((data) => {
        if (cancelled) return;
        writeCachedItems(cacheKey, data.items);
        setItems(data.items);
      })
      // keep showing whatever we already have if the refresh fails
      .catch((error) => Sentry.captureException(error))
      .finally(() => {
        if (!cancelled) setIsFetching(false);
      });
    return () => {
      cancelled = true;
    };
  }, [itemsUrl, cacheKey, locationKey]);

  return { items: items ?? item.items, isFetching };
}

// sessionStorage (not localStorage): scoped to the tab and dropped when it
// closes, which is as long as a cached nav list is useful anyway
const ITEMS_CACHE_PREFIX = "gooey:nav-items:";

function readCachedItems(cacheKey: string): NavWorkflowItem[] | null {
  try {
    const cached = sessionStorage.getItem(ITEMS_CACHE_PREFIX + cacheKey);
    if (!cached) return null;
    return JSON.parse(cached) as NavWorkflowItem[];
  } catch {
    // unavailable (private mode) or unparseable - fall back to fetching
    return null;
  }
}

function writeCachedItems(cacheKey: string, items: NavWorkflowItem[]) {
  try {
    sessionStorage.setItem(
      ITEMS_CACHE_PREFIX + cacheKey,
      JSON.stringify(items)
    );
  } catch {
    // storage unavailable or full - the list still works, it just won't warm up
  }
}

function isExternalHref(href: string): boolean {
  return /^(?:[a-z][a-z0-9+.-]*:|\/\/)/i.test(href);
}

import type { NavWorkflowItem } from "@gooey-types/navigation_sidebar_props";
import { useLocation } from "@remix-run/react";

type WorkflowListProps = {
  items: NavWorkflowItem[];
  indent?: boolean;
};

function normalizePath(path: string): string {
  return path.replace(/\/+$/, "") || "/";
}

export function hrefMatchesLocation(
  href: string,
  pathname: string,
  search: string
): boolean {
  let target: URL;
  try {
    target = new URL(href, "http://_"); // href is absolute; base is a no-op
  } catch {
    return false;
  }
  if (normalizePath(target.pathname) !== normalizePath(pathname)) return false;

  const here = new URLSearchParams(search);
  const runId = target.searchParams.get("run_id");
  const uid = target.searchParams.get("uid");
  if (runId || uid) {
    return runId === here.get("run_id") && uid === here.get("uid");
  }
  // Example link: a path match is enough, as long as we're not on a run of it.
  return !here.get("run_id");
}

function WorkflowRowItem({
  item,
  isActive,
}: {
  item: NavWorkflowItem;
  isActive: boolean;
}) {
  return (
    <a
      href={item.href}
      aria-current={isActive ? "page" : undefined}
      className={
        "d-flex align-items-center gap-2 py-2 px-2 sidebar-recent-item rounded" +
        (isActive ? " sidebar-recent-item--active" : "")
      }
    >
      <span className="d-flex align-items-center justify-content-center flex-shrink-0 sidebar-recent-item-icon">
        {item.image_url ? (
          <img
            src={item.image_url}
            alt=""
            width={20}
            height={20}
            className="nav-workflow-thumb rounded-circle flex-shrink-0"
          />
        ) : item.icon ? (
          // workflow_icon is FontAwesome icon HTML (or a bare emoji); render
          // both as-is rather than treating it as a class name.
          <span
            aria-hidden="true"
            dangerouslySetInnerHTML={{ __html: item.icon }}
          />
        ) : null}
      </span>
      <p
        className={
          "mb-0 text-truncate text-body" + (isActive ? " fw-semibold" : "")
        }
      >
        {item.title}
      </p>
    </a>
  );
}

export function WorkflowList({ items, indent = false }: WorkflowListProps) {
  const location = useLocation();
  if (items.length === 0) return null;

  return (
    <div className={indent ? "ps-4" : undefined}>
      {items.map((item, idx) => (
        <WorkflowRowItem
          key={idx}
          item={item}
          isActive={hrefMatchesLocation(
            item.href,
            location.pathname,
            location.search
          )}
        />
      ))}
    </div>
  );
}

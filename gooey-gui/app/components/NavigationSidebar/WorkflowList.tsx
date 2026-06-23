import type { NavWorkflowData } from "@gooey-types/navigation_sidebar_props";

type WorkflowListProps = {
  items: NavWorkflowData[];
  indent?: boolean;
};

function WorkflowRow({ item }: { item: NavWorkflowData }) {
  return (
    <div className="d-flex align-items-center gap-2 py-1 px-2" style={{ minWidth: 0 }}>
      {item.image_url ? (
        <img
          src={item.image_url}
          alt=""
          width={28}
          height={28}
          className="rounded object-fit-cover flex-shrink-0"
          style={{ borderRadius: 4 }}
        />
      ) : item.icon ? (
        <i
          className={item.icon}
          style={{ width: 28, textAlign: "center", flexShrink: 0, fontSize: 14 }}
        />
      ) : (
        <i
          className="fa-regular fa-clock"
          style={{ width: 28, textAlign: "center", flexShrink: 0, fontSize: 14 }}
        />
      )}
      <a
        href={item.href}
        className="text-body text-decoration-none text-truncate"
        style={{ minWidth: 0, fontSize: "0.875rem" }}
        title={item.title}
      >
        {item.title}
      </a>
    </div>
  );
}

export function WorkflowList({ items, indent = false }: WorkflowListProps) {
  if (items.length === 0) return null;

  return (
    <div className={indent ? "ps-3" : undefined}>
      {items.map((item, idx) => (
        <WorkflowRow key={idx} item={item} />
      ))}
    </div>
  );
}

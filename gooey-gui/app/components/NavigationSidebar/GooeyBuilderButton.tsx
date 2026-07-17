import clsx from "clsx";
import type { GooeyBuilderData } from "@gooey-types/navigation_sidebar_props";

export function GooeyBuilderButton({
  gooey_builder,
  compact,
  mobile = false,
}: {
  gooey_builder: GooeyBuilderData;
  compact: boolean;
  mobile?: boolean;
}) {
  return (
    <button
      type="button"
      className={clsx(
        "gooey-builder-btn btn b-1 bg-hover-light d-flex align-items-center position-relative",
        compact ? "justify-content-center p-1" : "gap-2 p-2",
        mobile ? "border-0" : "border b-1"
      )}
      title={gooey_builder.name}
      onClick={(e) => {
        e.stopPropagation();
        window.dispatchEvent(
          new CustomEvent(`${gooey_builder.event_key}:open`)
        );
      }}
    >
      <img
        src={gooey_builder.photo_url}
        alt=""
        width={mobile ? 24 : 28}
        height={mobile ? 24 : 28}
        className="rounded-circle flex-shrink-0"
      />
      {mobile && <span className="small ms-1">Ask</span>}
      {!compact && (
        <span className="d-flex flex-column text-start lh-sm small">
          <span className="text-muted small">Edit with AI</span>
          <span className="fw-semibold">{gooey_builder.name}</span>
        </span>
      )}
    </button>
  );
}

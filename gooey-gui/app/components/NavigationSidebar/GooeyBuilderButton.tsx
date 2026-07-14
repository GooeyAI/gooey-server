import clsx from "clsx";
import type { GooeyBuilderData } from "@gooey-types/navigation_sidebar_props";

// Matches the Sidebar `name`/`key` used for the Builder panel (sidebar_layout
// in widgets/sidebar.py). Sidebar.tsx persists its open state under this key,
// so the rail can read it to stay in sync across page navigations.
export const BUILDER_SIDEBAR_KEY = "builder-sidebar";

// URL fragment that Builder-run links in the rail carry (see
// widgets/navigation_sidebar.py). When present on arrival, the rail force-opens
// the Builder panel regardless of the persisted open/closed state.
export const OPEN_BUILDER_HASH = "#open-builder";

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
      title={"Gooey Builder"}
      onClick={(e) => {
        e.stopPropagation();
        window.dispatchEvent(new CustomEvent(`${BUILDER_SIDEBAR_KEY}:open`));
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
          <span className="text-muted small">Build with AI</span>
          <span className="fw-semibold">Ask Gooey</span>
        </span>
      )}
    </button>
  );
}

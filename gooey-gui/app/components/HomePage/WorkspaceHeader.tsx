import { RenderedMarkdown } from "~/renderedMarkdown";
import type { WorkspaceHeaderData } from "@gooey-types/home_page_props";

export function WorkspaceHeader({ header }: { header: WorkspaceHeaderData }) {
  return (
    <header className="mb-5">
      <div className="d-flex align-items-center gap-3 mb-2">
        {header.photo_url && (
          <img
            src={header.photo_url}
            alt=""
            className="rounded-3 flex-shrink-0 object-fit-cover"
            style={{ width: "64px", height: "64px" }}
          />
        )}
        <h1 className="m-0 d-inline-flex align-items-center gap-2">
          <span className="text-break">{header.name}</span>
          {header.settings_href && (
            <a
              href={header.settings_href}
              className="text-muted fs-6"
              aria-label="Workspace settings"
            >
              <i className="fa-solid fa-gear" aria-hidden="true" />
            </a>
          )}
        </h1>
      </div>
      {header.description && (
        <div className="text-muted w-75">
          <RenderedMarkdown body={header.description} lineClamp={2} />
        </div>
      )}
    </header>
  );
}

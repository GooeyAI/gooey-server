import type { IndustryTile } from "./types";

export function IndustryBrowser({ tiles }: { tiles: IndustryTile[] }) {
  return (
    <section className="mb-5">
      <h6 className="text-muted text-uppercase small mb-3">
        Browse by industry
      </h6>
      <div className="row row-cols-2 row-cols-md-3 row-cols-lg-5 g-3 d-flex align-items-stretch">
        {tiles.map((tile) => (
          <div key={tile.id} className="col">
            <a
              href={tile.href}
              className="d-flex flex-column h-100 p-3 border rounded-4 text-decoration-none text-body border-hover"
            >
              {tile.icon && (
                <div
                  className="fs-3 mb-2"
                  dangerouslySetInnerHTML={{ __html: tile.icon }}
                />
              )}
              <div className="fw-semibold">{tile.name}</div>
              {tile.description && (
                <div className="text-muted small mt-1">{tile.description}</div>
              )}
              <div className="d-flex align-items-center justify-content-between mt-auto pt-2 small">
                <span className="text-muted">
                  {tile.workflowCount} workflows
                </span>
                <span className="fw-semibold small">
                  <i className="fa-solid fa-arrow-right"></i>
                </span>
              </div>
            </a>
          </div>
        ))}
      </div>
    </section>
  );
}

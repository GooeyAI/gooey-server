import type { NewsItem } from "./types";

export function NewsFeed({ items }: { items: NewsItem[] }) {
  return (
    <section className="mb-5">
      <h6 className="text-muted text-uppercase small mb-3">News from Gooey</h6>
      <div className="row row-cols-1 row-cols-md-4 g-3 d-flex align-items-stretch">
        {items.map((item) => (
          <div key={item.id} className="col">
            <a
              href={item.href}
              className="d-flex flex-column h-100 border rounded-4 overflow-hidden text-decoration-none text-body hover-card"
            >
              <div className="ratio ratio-21x9 bg-light">
                {item.photoUrl && (
                  <img
                    src={item.photoUrl}
                    alt=""
                    className="w-100 h-100 object-fit-cover"
                  />
                )}
              </div>
              <div className="p-3 d-flex flex-column flex-grow-1">
                <div className="text-uppercase text-muted small mb-2">
                  {item.tag} · {item.age}
                </div>
                <div className="fw-semibold line-clamp-2">{item.headline}</div>
              </div>
            </a>
          </div>
        ))}
      </div>
    </section>
  );
}

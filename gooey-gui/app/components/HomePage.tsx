import { useState } from "react";

import "./HomePage.css";

type WorkflowCardData = {
  id: number;
  title: string;
  description?: string;
  workflowLabel?: string;
  authorName: string;
  authorPhotoUrl: string | null;
  imageUrl: string | null;
  updatedAt?: string;
  href: string;
};

type WorkflowTab = {
  id: number;
  title: string;
  icon: string;
  cards: WorkflowCardData[];
};

type IndustryTile = {
  id: number;
  tagId: number;
  name: string;
  icon: string;
  description: string;
  workflowCount: number;
  href: string;
};

type NewsItem = {
  id: number;
  headline: string;
  tag: string;
  photoUrl: string | null;
  age: string;
  href: string;
};

type HomePageProps = {
  greeting: string | null;
  workflowTabs: WorkflowTab[];
  recentWorkflows: WorkflowCardData[];
  savedWorkflows: WorkflowCardData[];
  industryTiles: IndustryTile[];
  newsItems: NewsItem[];
};

export function HomePage({
  greeting,
  workflowTabs,
  recentWorkflows,
  savedWorkflows,
  industryTiles,
  newsItems,
}: HomePageProps) {
  return (
    <div className="container-xxl my-4">
      {greeting && <h1 className="mb-5">Welcome, {greeting}.</h1>}
      {recentWorkflows.length > 0 && (
        <WorkflowGrid heading="Your recent workflows" items={recentWorkflows} />
      )}
      {savedWorkflows.length > 0 && (
        <WorkflowGrid heading="Your saved workflows" items={savedWorkflows} />
      )}
      {workflowTabs.length > 0 && <WorkflowPicker tabs={workflowTabs} />}
      {industryTiles.length > 0 && <IndustryBrowser tiles={industryTiles} />}
      {newsItems.length > 0 && <NewsFeed items={newsItems} />}
    </div>
  );
}

function WorkflowGrid({
  heading,
  items,
}: {
  heading: string;
  items: WorkflowCardData[];
}) {
  return (
    <section className="mb-5">
      <h4 className="mb-4">{heading}</h4>
      <div className="row row-cols-1 row-cols-md-3 g-3 d-flex align-items-stretch">
        {items.map((item) => (
          <div key={item.id} className="col">
            <WorkflowCard card={item} hideDescription showWorkflowType />
          </div>
        ))}
      </div>
    </section>
  );
}

function WorkflowCard({
  card,
  hideDescription = false,
  showWorkflowType = false,
}: {
  card: WorkflowCardData;
  hideDescription?: boolean;
  showWorkflowType?: boolean;
}) {
  return (
    <a
      href={card.href}
      className="d-flex h-100 p-3 align-items-stretch border rounded-4 gap-3 text-decoration-none text-body hover-card"
    >
      <div className="flex-grow-1 d-flex flex-column justify-content-between min-w-0">
        <div>
          {showWorkflowType && card.workflowLabel && (
            <div className="text-muted text-uppercase small mb-2">
              {card.workflowLabel}
            </div>
          )}
          <div className="fw-semibold mb-1 text-break line-clamp-2">
            {card.title}
          </div>
          {!hideDescription && card.description && (
            <div className="text-muted small line-clamp-2 text-break">
              {card.description}
            </div>
          )}
        </div>
        {(() => {
          const hasAuthor = !!(card.authorPhotoUrl || card.authorName);
          if (!hasAuthor && !card.updatedAt) return null;
          return (
            <div className="d-flex align-items-center gap-2 mt-2 small text-muted opacity-75">
              {hasAuthor && (
                <span className="d-inline-flex align-items-center gap-2 min-w-0">
                  {card.authorPhotoUrl && (
                    <img
                      src={card.authorPhotoUrl}
                      alt=""
                      className="rounded-circle flex-shrink-0 starter-thumb-author object-fit-cover"
                    />
                  )}
                  {card.authorName && (
                    <span className="text-break text-truncate">
                      {card.authorName}
                    </span>
                  )}
                </span>
              )}
              {card.updatedAt && (
                <span
                  className={
                    hasAuthor ? "ms-auto text-nowrap" : "text-nowrap"
                  }
                >
                  {card.updatedAt}
                </span>
              )}
            </div>
          );
        })()}
      </div>
      <WorkflowCardThumbnail title={card.title} imageUrl={card.imageUrl} />
    </a>
  );
}

function WorkflowPicker({ tabs }: { tabs: WorkflowTab[] }) {
  const [activeIdx, setActiveIdx] = useState(0);
  const activeTab = tabs[activeIdx];

  return (
    <section className="mb-5">
      <h4 className="mb-4">What will you build today?</h4>

      <div className="d-inline-flex p-1 rounded-pill mb-4 gap-1 align-items-center bg-light">
        {tabs.map((tab, i) => (
          <button
            key={tab.id}
            type="button"
            className={
              "btn rounded-pill px-3 py-2 border-0 d-flex align-items-center gap-2 text-body workflow-tab-pill " +
              (i === activeIdx ? "bg-white active" : "bg-transparent")
            }
            onClick={() => setActiveIdx(i)}
          >
            {tab.icon && (
              <span dangerouslySetInnerHTML={{ __html: tab.icon }} />
            )}
            {tab.title}
          </button>
        ))}
      </div>

      {activeTab.cards.length === 0 ? (
        <p className="text-muted small">No workflows yet — check back soon.</p>
      ) : (
        <div className="row row-cols-1 row-cols-md-3 g-3 d-flex align-items-stretch">
          {activeTab.cards.map((card) => (
            <div key={card.id} className="col">
              <WorkflowCard card={card} />
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function WorkflowCardThumbnail({
  title,
  imageUrl,
}: {
  title: string;
  imageUrl: string | null;
}) {
  if (imageUrl) {
    return (
      <img
        src={imageUrl}
        alt=""
        className="rounded flex-shrink-0 align-self-center starter-thumb object-fit-cover"
      />
    );
  }
  const letter = (title.trim().charAt(0) || "?").toUpperCase();
  return (
    <div className="rounded flex-shrink-0 bg-light text-muted d-flex align-items-center justify-content-center starter-thumb starter-thumb-letter">
      {letter}
    </div>
  );
}

function IndustryBrowser({ tiles }: { tiles: IndustryTile[] }) {
  return (
    <section className="mb-5">
      <h6 className="text-muted text-uppercase small mb-3">
        Browse by industry
      </h6>
      <div className="row row-cols-2 row-cols-md-5 g-3 d-flex align-items-stretch">
        {tiles.map((tile) => (
          <div key={tile.id} className="col">
            <a
              href={tile.href}
              className="d-flex flex-column h-100 p-3 border rounded-4 text-decoration-none text-body hover-card"
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
                  Browse <i className="fa-solid fa-arrow-right"></i>
                </span>
              </div>
            </a>
          </div>
        ))}
      </div>
    </section>
  );
}

function NewsFeed({ items }: { items: NewsItem[] }) {
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


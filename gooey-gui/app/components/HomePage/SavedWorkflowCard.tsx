import { PreviewContent } from "./PreviewContent";
import type { CardData } from "./types";
import { LineClamp } from "~/renderedHTML";

export function SavedWorkflowCard({ card }: { card: CardData }) {
  const hasAuthor = !!(card.authorPhotoUrl || card.authorName);
  const fallbackLetter = (card.title.trim().charAt(0) || "?").toUpperCase();

  const hasFooter =
    hasAuthor || card.updatedAt || card.runCount || card.accessBadge;

  return (
    <a
      href={card.href}
      className="d-flex h-100 p-3 align-items-stretch border rounded-4 gap-3 text-decoration-none text-body border-hover"
    >
      <div className="flex-grow-1 d-flex flex-column justify-content-between min-w-0">
        <div>
          <LineClamp lines={1} expandable={false}>
            <span className="fw-bold text-break m-0 small">{card.title}</span>
          </LineClamp>
          {card.description && (
            <div className="text-muted small line-clamp-2 text-break">
              {card.description}
            </div>
          )}
        </div>
        {hasFooter && (
          <div className="d-flex align-items-center gap-2 mt-2 small text-muted flex-wrap opacity-75">
            {hasAuthor && (
              <span className="d-inline-flex small align-items-center gap-2 min-w-0">
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
              <span className="d-inline-flex small align-items-center gap-1 text-nowrap">
                <i className="far fa-clock" aria-hidden="true" />
                {card.updatedAt}
              </span>
            )}
            {card.runCount ? (
              <span className="d-inline-flex small align-items-center gap-1 text-nowrap">
                <i className="fas fa-person-running" aria-hidden="true" />
                {card.runCount.toLocaleString()} runs
              </span>
            ) : null}
            {card.accessBadge && (
              <span className="d-inline-flex small align-items-center gap-1 text-nowrap">
                <span
                  dangerouslySetInnerHTML={{
                    __html: card.accessBadge.iconHtml,
                  }}
                />
                <span>{card.accessBadge.label}</span>
              </span>
            )}
          </div>
        )}
      </div>

      <div className="flex-shrink-0 align-self-center starter-thumb overflow-hidden rounded bg-light p-0">
        {card.preview ? (
          <PreviewContent preview={card.preview} />
        ) : (
          <div className="text-muted d-flex align-items-center justify-content-center h-100 w-100 starter-thumb-letter">
            {fallbackLetter}
          </div>
        )}
      </div>
    </a>
  );
}

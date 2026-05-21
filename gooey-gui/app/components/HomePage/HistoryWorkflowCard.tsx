import { PreviewContent } from "./PreviewContent";
import type { CardData } from "./types";

export function HistoryWorkflowCard({ card }: { card: CardData }) {
  const hasAuthor = !!(card.authorPhotoUrl || card.authorName);
  return (
    <a
      href={card.href}
      className="d-flex flex-column h-100 border rounded-4 overflow-hidden text-decoration-none text-body border-hover"
    >
      <div className="position-relative recent-card-preview bg-light p-0">
        {(card.workflowLabel || card.workflowEmoji) && (
          <span className="badge bg-white text-body rounded-pill px-2 py-1 small d-inline-flex align-items-center gap-1 fw-normal position-absolute top-0 start-0 m-2 shadow-lg z-1">
            {card.workflowEmoji && (
              <span aria-hidden="true">{card.workflowEmoji}</span>
            )}
            {card.workflowLabel && <span>{card.workflowLabel}</span>}
          </span>
        )}
        {card.preview && <PreviewContent preview={card.preview} />}
      </div>

      <div className="d-flex flex-column p-3 gap-2 border-top">
        <span className="fw-bold text-break line-clamp-1 m-0 small">
          {card.title}
        </span>
        <div className="d-flex align-items-center gap-2 small text-muted">
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
          {hasAuthor && card.updatedAt && <span>·</span>}
          {card.updatedAt && (
            <span className="text-nowrap">{card.updatedAt}</span>
          )}
        </div>
      </div>
    </a>
  );
}

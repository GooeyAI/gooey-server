import { useState } from "react";

import { GooeyImg, GooeyVideo } from "~/components/MediaTags";
import { LineClamp } from "~/renderedHTML";
import { RenderedMarkdown } from "~/renderedMarkdown";

import type {
  AuthorData,
  ChatPreview,
  IconPreview,
  MediaPreview,
  WorkflowCardData,
  WorkflowTabData,
} from "@gooey-types/home_page_props";

import { GooeyTooltip } from "../GooeyTooltip";

export type CardPreview = ChatPreview | MediaPreview | IconPreview;

function CardAuthor({ author }: { author: AuthorData | null }) {
  if (!author?.photo_url && !author?.name) return null;
  return (
    <span className="d-inline-flex align-items-center gap-2 min-w-0">
      {author?.photo_url && (
        <img
          src={author?.photo_url}
          alt=""
          className="rounded-circle flex-shrink-0 starter-thumb-author object-fit-cover"
        />
      )}
      {author?.name && (
        <span className="text-break text-truncate">{author?.name}</span>
      )}
    </span>
  );
}

export function PreviewContent({ preview }: { preview: CardPreview }) {
  switch (preview.type) {
    case "chat":
      return (
        <div className="d-flex flex-column justify-content-center gap-3 p-3 h-100">
          {preview.user_message && (
            <div className="d-flex justify-content-end">
              <div className="recent-card-chat-bubble border rounded-3 px-2 py-1 text-break">
                <LineClamp lines={2} expandable={false}>
                  {preview.user_message}
                </LineClamp>
              </div>
            </div>
          )}
          {preview.bot_message && (
            <div className="d-flex justify-content-start">
              <div className="recent-card-chat-bubble bg-white rounded-3 px-2 py-1 text-break line-clamp-3 container-margin-reset">
                <RenderedMarkdown
                  body={preview.bot_message}
                  lineClamp={3}
                  lineClampExpand={false}
                />
              </div>
            </div>
          )}
        </div>
      );
    case "image":
      return (
        <GooeyImg
          src={preview.url}
          previewImg={preview.preview_img ?? undefined}
        />
      );
    case "video":
      return (
        <GooeyVideo
          src={preview.url}
          previewImg={preview.preview_img ?? undefined}
          muted
          playsInline
          preload="metadata"
          autoPlay
          loop
        />
      );
    case "audio":
      return (
        <div className="d-flex flex-column justify-content-center h-100 px-3">
          <audio src={preview.url} controls className="w-100" />
          {preview.caption && (
            <div className="text-muted small mt-2 text-break line-clamp-2">
              {preview.caption}
            </div>
          )}
        </div>
      );
    case "icon":
      return (
        <div className="d-flex align-items-center justify-content-center h-100 text-muted">
          {preview.image_url ? (
            <img
              src={preview.image_url}
              alt=""
              className="recent-card-icon-img"
            />
          ) : preview.icon ? (
            <span
              className="saved-card-thumb-letter"
              dangerouslySetInnerHTML={{ __html: preview.icon }}
            />
          ) : null}
        </div>
      );
    default: {
      const _exhaustive: never = preview;
      return _exhaustive;
    }
  }
}

export function HistoryWorkflowCard({ card }: { card: WorkflowCardData }) {
  const hasAuthor = !!(card.author?.photo_url || card.author?.name);
  return (
    <a
      href={card.href}
      className="d-flex flex-column h-100 border rounded-4 overflow-hidden text-decoration-none text-body border-hover"
    >
      <div className="position-relative recent-card-preview bg-light p-0">
        {card.workflow_icon && (
          <span className="badge bg-white text-body rounded-pill px-2 py-1 small d-inline-flex align-items-center gap-1 fw-normal position-absolute top-0 start-0 m-2 shadow-lg z-1">
            <span
              aria-hidden="true"
              dangerouslySetInnerHTML={{ __html: card.workflow_icon }}
            />
          </span>
        )}
        {card.preview && <PreviewContent preview={card.preview} />}
      </div>

      <div className="d-flex flex-column p-3 gap-2 border-top">
        <span className="text-break text-truncate line-clamp-1 m-0">
          {card.title}
        </span>
        <div className="d-flex align-items-center gap-1 small">
          <CardAuthor author={card.author} />
          {hasAuthor && card.updated_at && <span>·</span>}
          {card.updated_at && (
            <span className="text-nowrap text-muted">{card.updated_at}</span>
          )}
        </div>
      </div>
    </a>
  );
}

export function SavedWorkflowCard({ card }: { card: WorkflowCardData }) {
  const hasAuthor = !!(card.author?.photo_url || card.author?.name);
  const fallbackLetter = (card.title.trim().charAt(0) || "?").toUpperCase();

  const hasFooter = !!(hasAuthor || card.updated_at || card.run_count);

  return (
    <a
      href={card.href}
      className="d-flex flex-column p-3 gap-2 border rounded-4 text-decoration-none text-body border-hover"
    >
      <div className="d-flex gap-3 align-items-stretch">
        <div className="flex-shrink-0 saved-card-thumb overflow-hidden rounded bg-light p-0">
          {card.preview ? (
            <PreviewContent preview={card.preview} />
          ) : (
            <div className="text-muted d-flex align-items-center justify-content-center h-100 w-100 saved-card-thumb-letter">
              {fallbackLetter}
            </div>
          )}
        </div>

        <div className="flex-grow-1 min-w-0">
          <div className="d-flex align-items-center gap-1 min-w-0">
            {card.access_badge && (
              <GooeyTooltip content={card.access_badge.label}>
                <span
                  className="flex-shrink-0 small text-muted d-inline-flex align-items-center"
                  dangerouslySetInnerHTML={{
                    __html: card.access_badge.icon_html,
                  }}
                />
              </GooeyTooltip>
            )}
            <span className="bold text-break text-truncate m-0">
              {card.title}
            </span>
          </div>
          {card.description && (
            <div className="text-muted small line-clamp-2 text-break mt-1">
              {card.description}
            </div>
          )}
        </div>
      </div>

      {hasFooter && (
        <div className="d-flex align-items-center gap-2 mt-1 small flex-nowrap">
          <CardAuthor author={card.author} />
          {hasAuthor && card.updated_at && <span>·</span>}
          {card.updated_at && (
            <span className="d-inline-flex small align-items-center gap-1 text-nowrap text-muted">
              <i className="far fa-clock" aria-hidden="true" />
              {card.updated_at}
            </span>
          )}
          {hasAuthor && card.run_count && card.updated_at && <span>·</span>}
          {card.run_count ? (
            <span className="d-inline-flex small align-items-center gap-1 text-nowrap text-muted">
              <i className="fas fa-person-running" aria-hidden="true" />
              {card.run_count.toLocaleString()} runs
            </span>
          ) : null}
        </div>
      )}

      {card.change_notes && (
        <div className="d-flex align-items-center gap-1 pt-2 border-top small text-muted text-truncate">
          <i
            className="fa-regular fa-money-check-pen flex-shrink-0"
            aria-hidden="true"
          />
          <span className="text-truncate small">{card.change_notes}</span>
        </div>
      )}
    </a>
  );
}

export function WorkflowPickerCard({ card }: { card: WorkflowCardData }) {
  const hasAuthor = !!(card.author?.photo_url || card.author?.name);
  const fallbackLetter = (card.title.trim().charAt(0) || "?").toUpperCase();

  return (
    <a
      href={card.href}
      className="d-flex h-100 p-3 align-items-stretch border rounded-4 gap-3 text-decoration-none text-body border-hover"
    >
      <div className="flex-grow-1 d-flex flex-column justify-content-between min-w-0">
        <div>
          <LineClamp lines={1} expandable={false}>
            <span className="fw-bold text-break m-0 bold">{card.title}</span>
          </LineClamp>
          {card.description && (
            <div className="text-muted small line-clamp-2 text-break">
              {card.description}
            </div>
          )}
        </div>
        {hasAuthor && (
          <div className="small text-muted">
            <CardAuthor author={card.author} />
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

export function WorkflowPicker({ tabs }: { tabs: WorkflowTabData[] }) {
  const [activeIdx, setActiveIdx] = useState(0);
  const activeTab = tabs[activeIdx];

  if (tabs.length === 0) return null;
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

      <div key={activeTab.id}>
        {activeTab.cards.length === 0 ? (
          <p className="text-muted small">
            No workflows yet — check back soon.
          </p>
        ) : (
          <div className="row row-cols-1 row-cols-md-2 row-cols-lg-3 g-3 d-flex align-items-stretch">
            {activeTab.cards.map((card) => (
              <div key={card.href} className="col">
                <WorkflowPickerCard card={card} />
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

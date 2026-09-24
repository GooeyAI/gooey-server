import "./RecipeAbout.css";

import clsx from "clsx";

import type {
  AboutAuthor,
  AboutCard,
  AboutGroup,
  AboutMoreInfo,
  RecipeAboutProps,
} from "@gooey-types/about_props";

/** The generator inlines discriminated unions rather than naming them, so the media type
 *  is read back off the props it belongs to - it cannot drift from what the server sends. */
type AboutMedia = NonNullable<RecipeAboutProps["media"]>;
import { useWorkspaceLayout } from "~/appShellContext";
import { useCopyToClipboard } from "~/useCopyToClipboard";
import type { CustomComponentProps } from "~/components";
import { RenderedHTML } from "~/renderedHTML";
import { RenderedMarkdown } from "~/renderedMarkdown";

import { useRecipeWorkspaceContext } from "../RecipeWorkspace";
import { layoutForEditorPane } from "../RecipeWorkspace/paneState";
import type { WorkspaceLayout } from "../RecipeWorkspace/paneState";

/** Cards per row before a group takes a second line. */
const MAX_COLS = 6;

/** What this workflow is: its portrait, who published it, and one panel holding what it is
 *  filed under, what it is, and how it is put together. */
export function RecipeAbout({
  media,
  headline,
  author,
  share_value,
  share_url,
  report_value,
  submit_intent_key,
  tags,
  notes,
  notes_line_clamp,
  groups,
  more_info,
  sdgs,
  stats,
}: CustomComponentProps & RecipeAboutProps) {
  const { config } = useRecipeWorkspaceContext();
  // One subscription for the surface. Called per card it was a media listener and a
  // hydration effect each, for the one callback a card actually uses.
  const { selectLayout, isNarrow } = useWorkspaceLayout(config);
  const hasPanel =
    !!tags.length || !!notes || !!groups.length || !!sdgs.length || !!stats;
  return (
    <div className="v2-about">
      {!!media && <MediaSlot media={media} />}
      {!!headline && <h1 className="v2-about-headline">{headline}</h1>}
      {!!author && (
        <AuthorBlock
          author={author}
          shareValue={share_value}
          shareUrl={share_url}
          submitIntentKey={submit_intent_key}
          moreInfo={more_info}
        />
      )}
      {hasPanel && (
        <div className="v2-about-panel">
          {!!tags.length && (
            <div className="v2-about-tags">
              {/* Names what the pills are for. Hidden: the pills read as tags already. */}
              <h3 className="visually-hidden">Related AI Workflows</h3>
              {tags.map((tag) => (
                <a
                  key={tag.href + tag.label_html}
                  className="v2-about-tag"
                  href={tag.href}
                >
                  <h4 className="v2-about-tag-label">
                    <RenderedHTML body={tag.label_html} />
                  </h4>
                </a>
              ))}
            </div>
          )}
          {!!notes && (
            <div>
              <h2 className="v2-about-section-title">Description</h2>
              <div className="container-margin-reset v2-about-notes">
                <RenderedMarkdown body={notes} lineClamp={notes_line_clamp} />
              </div>
            </div>
          )}
          {(!!sdgs.length || !!stats || !!groups.length) && (
            /* One flex row for all three kinds of group, so SDG, the stats and the config
               cards sit side by side and wrap together rather than stacking. */
            <div className="v2-about-groups">
              {!!sdgs.length && (
                <div className="v2-about-group">
                  <h3 className="v2-about-section-title">SDG</h3>
                  <div className="v2-about-sdgs">
                    {sdgs.map((sdg) => (
                      <a
                        key={sdg.number}
                        className="v2-about-sdg"
                        href={sdg.href}
                        title={`Goal ${sdg.number}: ${sdg.title}`}
                      >
                        <img src={sdg.icon_url} alt={sdg.title} />
                      </a>
                    ))}
                  </div>
                </div>
              )}
              {!!stats && (
                <div className="v2-about-group">
                  <h3 className="v2-about-section-title">{stats.title}</h3>
                  <div className="v2-about-stats">
                    {stats.cards.map((card) => (
                      <div key={card.label} className="v2-about-stat">
                        <span className="v2-about-stat-value">{card.value}</span>
                        <span className="v2-about-stat-label">{card.label}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {groups.map((group) => (
                <GroupBlock
                  key={group.title}
                  group={group}
                  submitIntentKey={submit_intent_key}
                  selectLayout={selectLayout}
                  isNarrow={isNarrow}
                />
              ))}
            </div>
          )}
        </div>
      )}
      {/* Closes the surface. Report is only offered to someone it can be attributed to,
          so logged out this row is the two policy links. */}
      <div className="v2-about-footer">
        <a className="v2-about-footer-link" href="https://gooey.ai/privacy">
          <i className="fa-regular fa-shield" />
          <span>Privacy</span>
        </a>
        <a className="v2-about-footer-link" href="https://gooey.ai/terms">
          <i className="fa-regular fa-file-pen" />
          <span>Terms</span>
        </a>
        {!!report_value && (
          // The submit-intent path Share uses: the form posts its submitter's name and
          // value, which reaches `_handle_menu_pick` and opens the dialog.
          <button
            type="submit"
            className="v2-about-footer-link"
            name={submit_intent_key}
            value={report_value}
            title="Report this workflow"
          >
            <i className="fa-regular fa-flag" />
            <span>Report</span>
          </button>
        )}
      </div>
    </div>
  );
}

/** The attribution, on the page rather than in the panel: it is who is speaking, and the
 *  panel is what they said. Share sits opposite it. */
function AuthorBlock({
  author,
  shareValue,
  shareUrl,
  submitIntentKey,
  moreInfo,
}: {
  author: AboutAuthor;
  shareValue?: string | null;
  shareUrl?: string | null;
  submitIntentKey: string;
  moreInfo?: AboutMoreInfo | null;
}) {
  const { copied, shareNatively } = useNativeShare(shareUrl);
  const row = (
    <div className="v2-about-author-row">
      <img className="v2-about-author-photo" src={author.photo_url} alt="" />
      <div className="v2-about-author-text">
        <span className="v2-about-author-name text-truncate">
          {author.name}
        </span>
        {!!author.subtitle && (
          <span className="v2-about-author-meta text-truncate">
            {author.subtitle}
          </span>
        )}
      </div>
    </div>
  );
  const hasActions = !!shareValue || !!shareUrl || !!moreInfo;
  return (
    <div className="v2-about-author">
      {author.href ? <a href={author.href}>{row}</a> : row}
      {hasActions && (
        // Grouped, so `space-between` separates the attribution from the buttons rather
        // than the buttons from each other.
        <div className="v2-about-author-actions">
          {!!shareValue && (
            // The same ShareIntent the bar's button posts, so one dialog opens either way.
            <button
              type="submit"
              className="v2-about-share"
              name={submitIntentKey}
              value={shareValue}
            >
              <i className="fa-regular fa-share-nodes" />
              <span>Share</span>
            </button>
          )}
          {!shareValue && !!shareUrl && (
            // Nobody to open the share dialog for, so the browser's own sheet takes the
            // url. `type="button"`: this must not submit the form it sits in.
            <button
              type="button"
              className="v2-about-share"
              onClick={shareNatively}
              title="Share this workflow"
            >
              <i className="fa-regular fa-share-nodes" />
              <span>{copied ? "Link copied" : "Share"}</span>
            </button>
          )}
          {!!moreInfo && (
            <a className="v2-about-share" href={moreInfo.href}>
              <i className="fa-regular fa-arrow-up-right-from-square" />
              <span>{moreInfo.text}</span>
            </a>
          )}
        </div>
      )}
    </div>
  );
}

/** The browser's share sheet, falling back to the clipboard where there is none - Firefox
 *  on the desktop has no `navigator.share`, and nor does any insecure context. */
function useNativeShare(url?: string | null) {
  const { copied, copyUrl } = useCopyToClipboard();
  const shareNatively = () => {
    if (!url) return;
    // A sheet the user dismisses rejects with AbortError; that is not a failure.
    if (navigator.share) {
      navigator.share({ title: document.title, url }).catch(() => {});
      return;
    }
    copyUrl(url);
  };
  return { copied, shareNatively };
}

function GroupBlock({
  group,
  submitIntentKey,
  selectLayout,
  isNarrow,
}: {
  group: AboutGroup;
  submitIntentKey: string;
  selectLayout: (next: WorkspaceLayout) => void;
  isNarrow: boolean;
}) {
  return (
    <div className="v2-about-group">
      <h3 className="v2-about-section-title">{group.title}</h3>
      {/* The column count follows the cards rather than `auto-fill`, which materialises
          every track that fits and made a two-card group as wide as a six-card one. */}
      <div
        className="v2-about-meta"
        style={
          {
            "--v2-about-cols": Math.min(group.cards.length, MAX_COLS),
          } as React.CSSProperties
        }
      >
        {group.cards.map((card) => (
          <MetaCard
            key={card.label}
            card={card}
            submitIntentKey={submitIntentKey}
            selectLayout={selectLayout}
            isNarrow={isNarrow}
          />
        ))}
      </div>
    </div>
  );
}

/** One tile. What it *is* is the caller's decision; what it looks like is `body`. */
function MetaCard({
  card,
  submitIntentKey,
  selectLayout,
  isNarrow,
}: {
  card: AboutCard;
  submitIntentKey: string;
  selectLayout: (next: WorkspaceLayout) => void;
  isNarrow: boolean;
}) {
  const { config, setActiveEditorPane } = useRecipeWorkspaceContext();
  const body = (
    <>
      <span className="v2-about-meta-head">
        <span className="v2-about-meta-icon">
          <RenderedHTML body={card.icon_html} />
        </span>
        <i className="fa-regular fa-chevron-right v2-about-meta-chevron" />
      </span>
      <h4 className="v2-about-meta-label">{card.label}</h4>
    </>
  );

  switch (card.target.kind) {
    case "link":
      return (
        <a className="v2-about-meta-card" href={card.target.href}>
          {body}
        </a>
      );
    case "submit":
      // The form copies its submitter's name and value into the state it posts, so this
      // reaches the same handler the top bar's chips do.
      return (
        <button
          type="submit"
          className="v2-about-meta-card"
          name={submitIntentKey}
          value={card.target.value}
        >
          {body}
        </button>
      );
    default: {
      const target = card.target;
      return (
        <button
          type="button"
          className="v2-about-meta-card"
          onClick={() => {
            selectLayout(
              layoutForEditorPane(
                target.layout,
                target.editor_pane,
                config.narrow_surface,
                isNarrow
              )
            );
            if (target.editor_pane) setActiveEditorPane(target.editor_pane);
          }}
        >
          {body}
        </button>
      );
    }
  }
}

/** The one slot at the head of the surface. Which of the three it is was decided server
 *  side, so this only draws it. */
function MediaSlot({ media }: { media: AboutMedia }) {
  switch (media.kind) {
    case "video":
      return (
        <video
          className="v2-about-media"
          src={media.url}
          controls
          playsInline
          preload="metadata"
        />
      );
    case "banner":
      return (
        <img
          className="v2-about-media v2-about-banner"
          src={media.url}
          alt=""
        />
      );
    default:
      return (
        <img
          className={clsx(
            "v2-about-photo",
            media.circle && "v2-about-photo-circle"
          )}
          src={media.url}
          alt=""
        />
      );
  }
}

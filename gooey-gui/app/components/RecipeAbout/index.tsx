import "./RecipeAbout.css";

import clsx from "clsx";

import type {
  AboutAuthor,
  AboutCard,
  AboutGroup,
  RecipeAboutProps,
} from "@gooey-types/about_props";
import { useWorkspaceLayout } from "~/appShellContext";
import { useCopyToClipboard } from "~/useCopyToClipboard";
import type { CustomComponentProps } from "~/components";
import { RenderedHTML } from "~/renderedHTML";
import { RenderedMarkdown } from "~/renderedMarkdown";

import { useRecipeWorkspaceContext } from "../RecipeWorkspace";
import { layoutForEditorPane, layoutsEqual } from "../RecipeWorkspace/paneState";
import type { WorkspaceLayout } from "../RecipeWorkspace/paneState";

/** Cards per row before a group takes a second line. */
const MAX_COLS = 6;

/** What this workflow is: its portrait, who published it, and one panel holding what it is
 *  filed under, what it is, and how it is put together. */
export function RecipeAbout({
  heading,
  heading_meta,
  photo_url,
  circle_photo,
  author,
  share_value,
  share_url,
  report_value,
  submit_intent_key,
  tags,
  notes,
  notes_line_clamp,
  groups,
}: CustomComponentProps & RecipeAboutProps) {
  const { config } = useRecipeWorkspaceContext();
  // One subscription for the surface. Called per card it was a media listener and a
  // hydration effect each, for the one callback a card actually uses.
  const { selectLayout, isNarrow } = useWorkspaceLayout(config);
  const hasPanel = !!tags.length || !!notes || !!groups.length;
  return (
    <div className="v2-about">
      <AboutViewSwitcher />
      {!!photo_url && (
        <img
          className={clsx(
            "v2-about-photo",
            circle_photo && "v2-about-photo-circle"
          )}
          src={photo_url}
          alt=""
        />
      )}
      {/* Below lg the bar leads with the logo, so the name is shown here instead. A `p`,
          not a heading: the page's one h1 is the bar's. */}
      <p className="v2-about-heading">{heading}</p>
      {!!heading_meta && <p className="v2-about-heading-meta">{heading_meta}</p>}
      {!!author && (
        <AuthorBlock
          author={author}
          shareValue={share_value}
          shareUrl={share_url}
          submitIntentKey={submit_intent_key}
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
          {!!groups.length && (
            <div className="v2-about-groups">
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

/** The view switcher, above About's content and below lg only.
 *
 *  Here rather than in the top bar: it belongs to the page, scrolls with it, and sticks to
 *  the top of the surface. The bar's pill is the drawer's trigger, not this.
 */
function AboutViewSwitcher() {
  const { config } = useRecipeWorkspaceContext();
  const { layout, selectLayout } = useWorkspaceLayout(config);
  const views = config.views.filter((view) => !view.desktop_only);
  if (views.length < 2) return null;
  return (
    <div className="v2-about-views d-lg-none" role="tablist">
      {views.map((view) => {
        const active = layoutsEqual(view.layout, layout);
        return (
          <button
            key={view.key}
            type="button"
            role="tab"
            aria-selected={active}
            className={clsx("v2-about-view", active && "v2-about-view--active")}
            onClick={() => selectLayout(view.layout)}
          >
            {!!view.icon_html && (
              <span
                className="v2-about-view-icon"
                dangerouslySetInnerHTML={{ __html: view.icon_html }}
              />
            )}
            {view.label}
          </button>
        );
      })}
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
}: {
  author: AboutAuthor;
  shareValue?: string | null;
  shareUrl?: string | null;
  submitIntentKey: string;
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
  return (
    <div className="v2-about-author">
      {author.href ? <a href={author.href}>{row}</a> : row}
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
        // Nobody to open the share dialog for, so the browser's own sheet takes the url.
        // `type="button"`: this must not submit the form it sits in.
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
    <div className={clsx("v2-about-group", `v2-about-group--${group.variant}`)}>
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
  // The platform's own colour, used only by the full-width deployment buttons below lg.
  const accent = card.accent
    ? ({ "--v2-about-accent": card.accent } as React.CSSProperties)
    : undefined;
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
        <a className="v2-about-meta-card" href={card.target.href} style={accent}>
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
          style={accent}
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

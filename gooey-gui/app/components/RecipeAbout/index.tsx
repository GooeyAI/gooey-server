import "./RecipeAbout.css";

import clsx from "clsx";

import type {
  AboutAuthor,
  AboutCard,
  AboutGroup,
  RecipeAboutProps,
} from "@gooey-types/about_props";
import { useWorkspaceLayout } from "~/appShellContext";
import type { CustomComponentProps } from "~/components";
import { RenderedHTML } from "~/renderedHTML";
import { RenderedMarkdown } from "~/renderedMarkdown";

import { layoutsEqual } from "../RecipeWorkspace/paneState";
import { useRecipeWorkspaceContext } from "../RecipeWorkspace";

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
  submit_intent_key,
  tags,
  notes,
  notes_line_clamp,
  groups,
}: CustomComponentProps & RecipeAboutProps) {
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
      {/* Below lg the top bar shows the logo at the scroll top, so the name lives here. */}
      <h1 className="v2-about-heading">{heading}</h1>
      {!!heading_meta && <p className="v2-about-heading-meta">{heading_meta}</p>}
      {!!author && (
        <AuthorBlock
          author={author}
          shareValue={share_value}
          submitIntentKey={submit_intent_key}
        />
      )}
      {hasPanel && (
        <div className="v2-about-panel">
          {!!tags.length && (
            <div className="v2-about-tags">
              {tags.map((tag) => (
                <a
                  key={tag.href + tag.label_html}
                  className="v2-about-tag"
                  href={tag.href}
                >
                  <RenderedHTML body={tag.label_html} />
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
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** The view switcher, above About's content and below lg only.
 *
 *  Here rather than in the top bar: it belongs to the page, scrolls with it, and sticks to
 *  the top of the surface as you go. The bar's pill is the drawer's trigger, not this.
 */
function AboutViewSwitcher() {
  const { config, setActiveEditorPane } = useRecipeWorkspaceContext();
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
            className={clsx(
              "v2-about-view",
              active && "v2-about-view--active"
            )}
            onClick={() => {
              selectLayout(view.layout);
              setActiveEditorPane("");
            }}
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
  submitIntentKey,
}: {
  author: AboutAuthor;
  shareValue?: string | null;
  submitIntentKey: string;
}) {
  const row = (
    <div className="v2-about-author-row">
      <img className="v2-about-author-photo" src={author.photo_url} alt="" />
      <div className="v2-about-author-text">
        <span className="v2-about-author-name">{author.name}</span>
        {!!author.subtitle && (
          <span className="v2-about-author-meta">{author.subtitle}</span>
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
    </div>
  );
}

function GroupBlock({
  group,
  submitIntentKey,
}: {
  group: AboutGroup;
  submitIntentKey: string;
}) {
  return (
    <div className={clsx("v2-about-group", `v2-about-group--${group.variant}`)}>
      <h2 className="v2-about-section-title">{group.title}</h2>
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
}: {
  card: AboutCard;
  submitIntentKey: string;
}) {
  const { config, setActiveEditorPane } = useRecipeWorkspaceContext();
  const { selectLayout } = useWorkspaceLayout(config);
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
      <span className="v2-about-meta-label">{card.label}</span>
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
            selectLayout(target.layout);
            if (target.editor_pane) setActiveEditorPane(target.editor_pane);
          }}
        >
          {body}
        </button>
      );
    }
  }
}

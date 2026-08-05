import "./RecipeTopBar.css";

import clsx from "clsx";
import { Fragment, useEffect, useRef, useState } from "react";
import type { CustomComponentProps } from "~/components";
import type {
  RecipeTopBarProps,
  TopBarMenuItem,
} from "@gooey-types/recipe_top_bar_props";
import { Link } from "@remix-run/react";

/** Raw FontAwesome html arrives from python, the same way NavItemData.icon does. */
function Icon({ html, className }: { html?: string; className?: string }) {
  if (!html) return null;
  return (
    <span className={className} dangerouslySetInnerHTML={{ __html: html }} />
  );
}

function useDismissOnOutsideClick(onDismiss: () => void) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const handle = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onDismiss();
    };
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, [onDismiss]);
  return ref;
}

type MenuEntry = TopBarMenuItem & { mobileOnly?: boolean; heading?: boolean };

// the Publish menu's own entries, distinguishable from anything the server declares
const PUBLISH_ITEM_KEY = "--topbar-item-publish";
const SHARE_ITEM_KEY = "--topbar-item-share";
const API_ITEM_KEY = "--topbar-item-api";

function Menu({
  items,
  open,
  onPick,
}: {
  items: MenuEntry[];
  open: boolean;
  onPick: (item: TopBarMenuItem) => void;
}) {
  if (!open || !items.length) return null;
  return (
    <div className="gooey-topbar-menu">
      {items.map((item) =>
        item.heading ? (
          <div
            key={item.key}
            className={clsx(
              "gooey-topbar-menu-heading",
              item.mobileOnly && "d-lg-none",
            )}
          >
            {item.label}
          </div>
        ) : item.href ? (
          <Link
            key={item.key}
            to={item.href}
            className={clsx(
              "gooey-topbar-menu-item",
              item.is_danger && "text-danger",
              item.mobileOnly && "d-lg-none",
            )}
          >
            <Icon html={item.icon} className="gooey-topbar-menu-icon" />
            {item.label}
          </Link>
        ) : (
          <button
            key={item.key}
            type="button"
            className={clsx(
              "gooey-topbar-menu-item",
              item.is_danger && "text-danger",
              item.mobileOnly && "d-lg-none",
            )}
            onClick={() => onPick(item)}
          >
            <Icon html={item.icon} className="gooey-topbar-menu-icon" />
            {item.label}
          </button>
        ),
      )}
    </div>
  );
}

export function RecipeTopBar({
  title,
  photo_url,
  circle_photo,
  author,
  tabs,
  immersive_on_mobile,
  overflow_items,
  title_menu_items,
  integrations,
  publish_label,
  publish_key,
  has_unpublished_changes,
  api_href,
  share_key,
  share_icon,
  menu_key,
  run_key,
  viewport_wide_key,
  run_label,
  run_disabled,
  is_running,
  cost_label,
  cost_href,
  cost_title,
  onChange,
  state,
}: CustomComponentProps & RecipeTopBarProps) {
  const [titleMenuOpen, setTitleMenuOpen] = useState(false);
  const [overflowOpen, setOverflowOpen] = useState(false);
  const [publishMenuOpen, setPublishMenuOpen] = useState(false);

  const titleMenuRef = useDismissOnOutsideClick(() => setTitleMenuOpen(false));
  const overflowRef = useDismissOnOutsideClick(() => setOverflowOpen(false));
  const publishMenuRef = useDismissOnOutsideClick(() => setPublishMenuOpen(false));

  // mutate-then-notify: the server pops these keys on the next render
  const fire = (key: string, value: unknown = true) => {
    if (!key) return;
    state[key] = value;
    onChange();
  };

  // Where a run lands is the server's call, but Split - the only tab showing output beside
  // the inputs - exists on wide screens only, and the server cannot see the viewport. So
  // report which side of the line we are on. Deliberately no onChange(): this is not an
  // action, and the value rides along with the next post, which every run is.
  useEffect(() => {
    if (!viewport_wide_key) return;
    // the counterpart of the `max-width: 991.98px` block in RecipeTopBar.css, which is
    // what actually hides .gooey-topbar-tab-desktop-only
    const mq = window.matchMedia("(min-width: 992px)");
    const sync = () => {
      state[viewport_wide_key] = mq.matches;
    };
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, [viewport_wide_key, state]);

  // What the Publish control offers. `publish_label` is permission-derived (Update / Save
  // and Run / Save as New); Share only appears when the user may change visibility, and
  // its icon is the current setting, so it doubles as a read-out.
  const publishEntries: MenuEntry[] = [];
  if (publish_label) {
    publishEntries.push({
      key: PUBLISH_ITEM_KEY,
      label: publish_label,
      icon: '<i class="fa-regular fa-floppy-disk"></i>',
      href: null,
      is_danger: false,
    });
  }
  if (share_key) {
    publishEntries.push({
      key: SHARE_ITEM_KEY,
      label: "Share",
      icon: share_icon,
      href: null,
      is_danger: false,
    });
  }
  // Shipping this workflow over HTTP is the third way to publish it. A plain link, so it
  // needs no key round-trip - Menu renders any entry with an href as a <Link>.
  if (api_href) {
    publishEntries.push({
      key: API_ITEM_KEY,
      label: "API",
      icon: '<i class="fa-regular fa-code"></i>',
      href: api_href,
      is_danger: false,
    });
  }

  // Below lg the chips and the title compete for one row and the title always loses, so
  // the chips move into the overflow menu. Both lists are rendered and CSS picks one - no
  // media-query JS, and the chip count stops mattering. Publish folds in the same way:
  // there is one menu on a phone, not a menu plus a button.
  const overflowEntries: MenuEntry[] = [
    // the actions first - they are what the menu is for on a phone
    ...publishEntries.map((it) => ({ ...it, mobileOnly: true })),
    ...overflow_items,
    // ...then the channels this workflow is live on, under their own label so a long list
    // of them cannot be mistaken for more actions
    ...(integrations.length
      ? [
          {
            key: "--topbar-heading-deployments",
            label: "Deployments",
            icon: "",
            href: null,
            is_danger: false,
            mobileOnly: true,
            heading: true,
          },
        ]
      : []),
    ...integrations.map((it, i) => ({
      key: it.key || it.href || `integration-${i}`,
      label: it.label,
      icon: it.icon,
      href: it.href ?? null,
      is_danger: false,
      mobileOnly: true,
    })),
  ];
  // with nothing but mobile-only entries the button itself has no desktop purpose
  const overflowDesktopOnly = overflow_items.length === 0;

  const pickMenuItem = (item: TopBarMenuItem) => {
    setTitleMenuOpen(false);
    setOverflowOpen(false);
    setPublishMenuOpen(false);
    // these two are the component's own entries, not server-declared menu items, so they
    // go straight to their keys instead of round-tripping through menu_key
    if (item.key === PUBLISH_ITEM_KEY) return fire(publish_key);
    if (item.key === SHARE_ITEM_KEY) return fire(share_key);
    fire(menu_key, item.key);
  };

  return (
    <div
      className={clsx(
        "gooey-topbar",
        immersive_on_mobile && "gooey-topbar-immersive"
      )}
    >
      <div className="gooey-topbar-left">
        {photo_url && (
          <img
            src={photo_url}
            alt=""
            className={clsx(
              "gooey-topbar-avatar",
              circle_photo && "gooey-topbar-avatar-circle"
            )}
          />
        )}

        <div className="gooey-topbar-titleblock" ref={titleMenuRef}>
          <button
            type="button"
            className="gooey-topbar-title"
            onClick={() => setTitleMenuOpen((v) => !v)}
            disabled={!title_menu_items.length}
          >
            <span className="gooey-topbar-title-text">{title}</span>
            {!!title_menu_items.length && (
              <i className="fa-regular fa-chevron-down gooey-topbar-chevron" />
            )}
          </button>
          {author &&
            (author.href ? (
              <a className="gooey-topbar-author" href={author.href}>
                {author.label}
              </a>
            ) : (
              <span className="gooey-topbar-author">{author.label}</span>
            ))}
          <Menu
            items={title_menu_items}
            open={titleMenuOpen}
            onPick={pickMenuItem}
          />
        </div>

        {/* The collapse control lives on the Builder panel's own right edge, not here -
            see `.v2-builder-close`. Next to the title it read as belonging to the workflow
            rather than to the panel it closes. */}
      </div>

      {/* A single-tab recipe (media gen, bulk/eval) renders no pill group at all. */}
      {tabs.length > 1 && (
        <div className="gooey-topbar-tabs">
          {tabs.map((tab) => (
            <Link
              key={tab.slug}
              to={tab.href}
              className={clsx(
                "gooey-topbar-tab",
                tab.is_active && "gooey-topbar-tab-active",
                tab.desktop_only && "gooey-topbar-tab-desktop-only"
              )}
              // no title: these carry a visible label, so a tooltip repeating it is noise.
              // `aria-current` is the part that was missing - the active pill is styled, which
              // says nothing to a screen reader.
              aria-current={tab.is_active ? "page" : undefined}
            >
              <Icon html={tab.icon} className="gooey-topbar-tab-icon" />
              {tab.label}
            </Link>
          ))}
        </div>
      )}

      <div className="gooey-topbar-right">
        {!!overflowEntries.length && (
          <div className="gooey-topbar-overflow-wrap" ref={overflowRef}>
            <button
              type="button"
              className={clsx(
                "gooey-topbar-overflow-btn",
                overflowDesktopOnly && "d-lg-none"
              )}
              onClick={() => setOverflowOpen((v) => !v)}
              title="More actions"
              aria-label="More actions"
              aria-haspopup="menu"
              aria-expanded={overflowOpen}
            >
              <i className="fa-solid fa-ellipsis" />
            </button>
            <Menu
              items={overflowEntries}
              open={overflowOpen}
              onPick={pickMenuItem}
            />
          </div>
        )}

        {/* At most ONE chip is ever labelled, and none at all once there are more than two.
            The pill group is centred, so the right cluster only gets half the bar's slack; a
            workflow deployed to three channels has enough chips that even one label pushes the
            cluster over the pills. Unlabelled chips keep their name in the tooltip, and every
            channel appears with its full label in the ... menu regardless. */}
        {integrations.map((integration, i) => {
          const labelled = i === 0 && integrations.length <= 2;
          const className = clsx(
            "gooey-topbar-integration d-none d-lg-inline-flex",
            labelled && "gooey-topbar-integration--labelled",
            integration.color && "gooey-topbar-integration-brand"
          );
          const style = integration.color
            ? { backgroundColor: integration.color }
            : undefined;
          const content = (
            <Fragment>
              <Icon html={integration.icon} />
              {labelled && (
                <span className="gooey-topbar-integration-label">
                  {integration.label}
                </span>
              )}
            </Fragment>
          );
          // aria-label as well as title: every chip past the first renders no text at all, so
          // the tooltip is the only thing naming it and `title` alone is not a reliable
          // accessible name
          return integration.href ? (
            <a
              key={integration.href}
              href={integration.href}
              className={className}
              style={style}
              title={integration.label}
              aria-label={integration.label}
            >
              {content}
            </a>
          ) : (
            <button
              key={integration.key || i}
              type="button"
              className={className}
              style={style}
              title={integration.label}
              aria-label={integration.label}
              onClick={() => fire(menu_key, integration.key)}
            >
              {content}
            </button>
          );
        })}

        {/* One control rather than two buttons: Publish opens Update and Share. Below lg
            it is hidden entirely and the same two entries live in the ... menu, which is
            the only menu on a phone. */}
        {!!publishEntries.length && (
          <div
            className="gooey-topbar-overflow-wrap d-none d-lg-block"
            ref={publishMenuRef}
          >
            <button
              type="button"
              className="gooey-topbar-publish"
              onClick={() => setPublishMenuOpen((v) => !v)}
              title={
                has_unpublished_changes
                  ? "Publish (unpublished changes)"
                  : "Publish"
              }
              aria-label="Publish"
              aria-haspopup="menu"
              aria-expanded={publishMenuOpen}
            >
              <i className="fa-regular fa-floppy-disk" />
              <span className="gooey-topbar-btn-label">Publish</span>
              <i className="fa-regular fa-chevron-down gooey-topbar-chevron" />
              {has_unpublished_changes && (
                <span className="gooey-topbar-dot" title="Unpublished changes" />
              )}
            </button>
            <Menu
              items={publishEntries}
              open={publishMenuOpen}
              onPick={pickMenuItem}
            />
          </div>
        )}

        {/* `cost_label` on its own is a bare price. The tooltip names what it is and appends
            any per-recipe note; the aria-label says it outright, since "$0.05" read aloud in
            a row of controls is meaningless. */}
        {!!cost_label &&
          (() => {
            const costName = `Run cost: ${cost_label}`;
            const costTip = cost_title ? `${costName} (${cost_title})` : costName;
            return cost_href ? (
              <a
                className="gooey-topbar-cost"
                href={cost_href}
                title={costTip}
                aria-label={costTip}
              >
                {cost_label}
              </a>
            ) : (
              <span
                className="gooey-topbar-cost"
                title={costTip}
                aria-label={costTip}
              >
                {cost_label}
              </span>
            );
          })()}

        {!!cost_label && !!run_key && (
          <span className="gooey-topbar-sep" aria-hidden="true">
            /
          </span>
        )}

        {!!run_key && (
          <button
            type="button"
            className={clsx(
              "gooey-topbar-run",
              is_running && "gooey-topbar-run-stop"
            )}
            disabled={run_disabled}
            onClick={() => fire(run_key)}
            // `.gooey-topbar-btn-label` is hidden below lg, so on a phone this is an
            // unlabelled icon - the tooltip and aria-label are its only name there
            title={is_running ? "Stop this run" : run_label}
            aria-label={is_running ? "Stop this run" : run_label}
          >
            {is_running ? (
              <i className="fa-regular fa-xmark-large" />
            ) : (
              <i className="fa-solid fa-play" />
            )}
            <span className="gooey-topbar-btn-label">
              {is_running ? "Stop" : run_label}
            </span>
          </button>
        )}
      </div>
    </div>
  );
}

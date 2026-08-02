import "./RecipeTopBar.css";

import clsx from "clsx";
import { useEffect, useRef, useState } from "react";
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

function Menu({
  items,
  open,
  onPick,
}: {
  items: TopBarMenuItem[];
  open: boolean;
  onPick: (item: TopBarMenuItem) => void;
}) {
  if (!open || !items.length) return null;
  return (
    <div className="gooey-topbar-menu">
      {items.map((item) =>
        item.href ? (
          <Link
            key={item.key}
            to={item.href}
            className={clsx(
              "gooey-topbar-menu-item",
              item.is_danger && "text-danger",
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
  overflow_items,
  title_menu_items,
  integrations,
  publish_label,
  publish_key,
  has_unpublished_changes,
  menu_key,
  run_key,
  run_label,
  run_disabled,
  is_running,
  cost_label,
  cost_href,
  cost_title,
  builder_toggle_key,
  onChange,
  state,
}: CustomComponentProps & RecipeTopBarProps) {
  const [titleMenuOpen, setTitleMenuOpen] = useState(false);
  const [overflowOpen, setOverflowOpen] = useState(false);

  const titleMenuRef = useDismissOnOutsideClick(() => setTitleMenuOpen(false));
  const overflowRef = useDismissOnOutsideClick(() => setOverflowOpen(false));

  // mutate-then-notify: the server pops these keys on the next render
  const fire = (key: string, value: unknown = true) => {
    if (!key) return;
    state[key] = value;
    onChange();
  };

  const pickMenuItem = (item: TopBarMenuItem) => {
    setTitleMenuOpen(false);
    setOverflowOpen(false);
    fire(menu_key, item.key);
  };

  return (
    <div className="gooey-topbar">
      <div className="gooey-topbar-left">
        {photo_url && (
          <img
            src={photo_url}
            alt=""
            className={clsx(
              "gooey-topbar-avatar",
              circle_photo && "gooey-topbar-avatar-circle",
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

        {!!builder_toggle_key && (
          <button
            type="button"
            className="gooey-topbar-iconbtn"
            title="Toggle the Gooey Builder panel"
            onClick={() => fire(builder_toggle_key, !state[builder_toggle_key])}
          >
            <i className="fa-regular fa-sidebar" />
          </button>
        )}
      </div>

      {/* A single-tab recipe (media gen, bulk/eval) renders no pill group at all. */}
      {tabs.length > 1 && (
        <div className="gooey-topbar-tabs" ref={overflowRef}>
          {tabs.map((tab) => (
            <Link
              key={tab.slug}
              to={tab.href}
              className={clsx(
                "gooey-topbar-tab",
                tab.is_active && "gooey-topbar-tab-active",
              )}
            >
              <Icon html={tab.icon} className="gooey-topbar-tab-icon" />
              {tab.label}
            </Link>
          ))}
          {!!overflow_items.length && (
            <>
              <button
                type="button"
                className="gooey-topbar-tab gooey-topbar-overflow"
                onClick={() => setOverflowOpen((v) => !v)}
                aria-label="More"
              >
                <i className="fa-solid fa-ellipsis" />
              </button>
              <Menu
                items={overflow_items}
                open={overflowOpen}
                onPick={pickMenuItem}
              />
            </>
          )}
        </div>
      )}

      <div className="gooey-topbar-right">
        {integrations.map((integration) => (
          <a
            key={integration.href}
            href={integration.href}
            className="gooey-topbar-integration"
            style={
              integration.color ? { backgroundColor: integration.color } : undefined
            }
            title={integration.label}
          >
            <Icon html={integration.icon} />
          </a>
        ))}

        {!!publish_label && (
          <button
            type="button"
            className="gooey-topbar-publish"
            onClick={() => fire(publish_key)}
          >
            {publish_label}
            {has_unpublished_changes && (
              <span className="gooey-topbar-dot" title="Unpublished changes" />
            )}
          </button>
        )}

        {!!cost_label &&
          (cost_href ? (
            <a
              className="gooey-topbar-cost"
              href={cost_href}
              title={cost_title || undefined}
            >
              {cost_label}
            </a>
          ) : (
            <span className="gooey-topbar-cost" title={cost_title || undefined}>
              {cost_label}
            </span>
          ))}

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
              is_running && "gooey-topbar-run-stop",
            )}
            disabled={run_disabled}
            onClick={() => fire(run_key)}
          >
            {is_running ? (
              <i className="fa-regular fa-xmark-large" />
            ) : (
              <i className="fa-solid fa-play" />
            )}
            <span className="gooey-topbar-run-label">
              {is_running ? "Stop" : run_label}
            </span>
          </button>
        )}
      </div>
    </div>
  );
}

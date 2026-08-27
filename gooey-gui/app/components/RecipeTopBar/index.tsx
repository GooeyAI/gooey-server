import "./RecipeTopBar.css";

import clsx from "clsx";
import { Fragment, useEffect, useRef, useState } from "react";
import type { CustomComponentProps } from "~/components";
import type {
  RecipeTopBarProps,
  TopBarMenuItem,
} from "@gooey-types/recipe_top_bar_props";
import { Link, useNavigate } from "@remix-run/react";
import type { RecipeView } from "../RecipeWorkspace/paneState";
import {
  activeTabView,
  paneVisibility,
  selectedWorkspaceView,
  shownLayout,
  viewAfterRun,
  viewForLayout,
  workspaceTargetForView,
} from "../RecipeWorkspace/paneState";
import { usePaneLayout } from "../RecipeWorkspace/usePaneLayout";
import { NAV_DRAWER_OPEN_EVENT } from "../NavigationSidebar/navDrawer";
import { MobileActionSheet, type SheetEntry } from "./MobileActionSheet";

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
const DEPLOY_ITEM_KEY = "--topbar-item-deploy";

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
              item.mobileOnly && "d-lg-none"
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
              item.mobileOnly && "d-lg-none"
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
              item.mobileOnly && "d-lg-none"
            )}
            onClick={() => onPick(item)}
          >
            <Icon html={item.icon} className="gooey-topbar-menu-icon" />
            {item.label}
          </button>
        )
      )}
    </div>
  );
}

export function RecipeTopBar({
  title,
  photo_url,
  circle_photo,
  author,
  views,
  storage_key,
  initial_view,
  editor_full_width,
  narrow_pane,
  workspace_href,
  workspace_active,
  overflow_items,
  title_menu_items,
  integrations,
  publish_label,
  publish_key,
  has_unpublished_changes,
  api_href,
  share_key,
  share_icon,
  share_copy_url,
  menu_key,
  run_key,
  run_label,
  run_disabled,
  is_running,
  cost_label,
  cost_href,
  cost_title,
  view_only,
  crumb_label,
  deploy_href,
  builder_event_key,
  builder_new_event,
  history_href,
  onChange,
  state,
}: CustomComponentProps & RecipeTopBarProps) {
  const [shareCopied, setShareCopied] = useState(false);
  // the tick is the only feedback a copy gets, so it needs a fallback
  const copyShareUrl = () => {
    navigator.clipboard
      ?.writeText(share_copy_url)
      .then(() => {
        setShareCopied(true);
        setTimeout(() => setShareCopied(false), 2000);
      })
      .catch(() => window.prompt("Copy this link", share_copy_url));
  };

  const [sheetOpen, setSheetOpen] = useState(false);
  // Mirrors the Builder panel. Seeded from the server, then kept in step by the panel's
  // `:changed` announcement, which is the authority - the commands can be missed.
  const [builderOpen, setBuilderOpen] = useState(
    Boolean(builder_event_key && state[builder_event_key])
  );
  const [titleMenuOpen, setTitleMenuOpen] = useState(false);
  const [overflowOpen, setOverflowOpen] = useState(false);
  const [publishMenuOpen, setPublishMenuOpen] = useState(false);
  const navigate = useNavigate();
  const { layout, storedLayout, hydrated, selectView } = usePaneLayout(
    storage_key,
    initial_view,
    narrow_pane
  );
  // The shown layout, so the bar names the arrangement actually on screen.
  const activeView = viewForLayout(shownLayout(layout, editor_full_width));
  const selectedView = selectedWorkspaceView(activeView, workspace_active);
  // Which pill is lit, and what the crumb reads - see `activeTabView` for why this is not
  // simply the view on screen.
  const activeSlug = activeTabView(
    views.map((view) => view.slug),
    selectedView,
    workspace_active ? viewForLayout(storedLayout) : null
  );
  const activeViewSpec = views.find((view) => view.slug === activeSlug);
  const chooseView = (view: RecipeView) => {
    selectView(view);
    const target = workspaceTargetForView(workspace_active, workspace_href);
    if (target) {
      navigate(target);
    }
  };
  const handleRun = () => {
    if (workspace_active) {
      selectView(viewAfterRun(activeView, is_running));
    }
    fire(run_key);
  };

  useEffect(() => {
    if (!builder_event_key) return;
    const onOpen = () => setBuilderOpen(true);
    const onClose = () => setBuilderOpen(false);
    const onChanged = (e: Event) => {
      const open = (e as CustomEvent<{ open?: boolean }>).detail?.open;
      if (typeof open === "boolean") setBuilderOpen(open);
    };
    window.addEventListener(`${builder_event_key}:open`, onOpen);
    window.addEventListener(`${builder_event_key}:close`, onClose);
    window.addEventListener(`${builder_event_key}:changed`, onChanged);
    return () => {
      window.removeEventListener(`${builder_event_key}:open`, onOpen);
      window.removeEventListener(`${builder_event_key}:close`, onClose);
      window.removeEventListener(`${builder_event_key}:changed`, onChanged);
    };
  }, [builder_event_key]);

  // On a phone a workflow opens on Ask Gooey, so the panel shows itself until this session
  // has picked a view - an absent stored layout being what "has not picked" means.
  // 1140px is the panel's own breakpoint, not lg: above it the panel shares the screen.
  useEffect(() => {
    if (!builder_event_key) return;
    // Only on the workspace; elsewhere the panel would cover a page the user navigated to.
    if (!workspace_active) return;
    // A visitor lands on About; Remix is how they opt into a chat.
    if (view_only) return;
    if (window.innerWidth >= 1140) return;
    let chosen: string | null = null;
    try {
      chosen = window.sessionStorage.getItem(storage_key);
    } catch {
      // Storage can be unavailable; treat that as nothing chosen yet.
    }
    if (chosen) return;
    window.dispatchEvent(new CustomEvent(`${builder_event_key}:open`));
  }, [builder_event_key, storage_key]);

  // Below lg the bar is a navigation stack. Its root is Ask Gooey where the page has a
  // Builder, and the entry view otherwise; a tab that is not the workspace is never the root.
  // Assume the root until hydrated, since before then the layout is only `initial_view`.
  const atRoot =
    workspace_active &&
    (!hydrated ||
      (builder_event_key ? builderOpen : selectedView === initial_view));
  // The server names a non-workspace tab; on the workspace it is the view on screen.
  const crumb = crumb_label || activeViewSpec?.label || "";
  const previewable = views.some((view) => view.slug === "preview");

  const openNavDrawer = () =>
    window.dispatchEvent(new CustomEvent(NAV_DRAWER_OPEN_EVENT));

  const setBuilder = (open: boolean) => {
    if (!builder_event_key) return;
    window.dispatchEvent(
      new CustomEvent(`${builder_event_key}:${open ? "open" : "close"}`)
    );
  };

  // Back a level: to the workspace from another tab, else to Ask Gooey or the entry view.
  const goBack = () => {
    if (!workspace_active) return chooseView("edit");
    if (builder_event_key) return setBuilder(true);
    chooseView(initial_view);
  };

  // Puts Ask Gooey away first, or the selected pane renders behind it.
  const showView = (view: RecipeView) => {
    setBuilder(false);
    chooseView(view);
  };

  const titleMenuRef = useDismissOnOutsideClick(() => setTitleMenuOpen(false));
  const overflowRef = useDismissOnOutsideClick(() => setOverflowOpen(false));
  const publishMenuRef = useDismissOnOutsideClick(() =>
    setPublishMenuOpen(false)
  );

  // mutate-then-notify: the server pops these keys on the next render
  const fire = (key: string, value: unknown = true) => {
    if (!key) return;
    state[key] = value;
    onChange();
  };

  // What the Publish control offers. `publish_label` is permission-derived.
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
  // The server sets exactly one of these: a visibility dialog, or a link to copy.
  if (share_key || share_copy_url) {
    publishEntries.push({
      key: SHARE_ITEM_KEY,
      label: shareCopied ? "Link copied" : "Share",
      icon: share_icon,
      href: null,
      is_danger: false,
    });
  }
  // A plain link - Menu renders any entry with an href as a <Link>.
  if (api_href) {
    publishEntries.push({
      key: API_ITEM_KEY,
      label: "API",
      icon: '<i class="fa-regular fa-code"></i>',
      href: api_href,
      is_danger: false,
    });
  }

  // A route rather than a pane, so a link like the API entry above.
  if (deploy_href) {
    publishEntries.push({
      key: DEPLOY_ITEM_KEY,
      label: "Deploy",
      icon: '<i class="fa-regular fa-rocket"></i>',
      href: deploy_href,
      is_danger: false,
    });
  }

  // Below lg the chips and Publish fold into this menu. Both lists render and CSS picks
  // one, so no media-query JS and the chip count does not matter.
  const overflowEntries: MenuEntry[] = [
    // the actions first - they are what the menu is for on a phone
    ...publishEntries.map((it) => ({ ...it, mobileOnly: true })),
    ...overflow_items,
    // ...then the deployed channels, under a heading so they do not read as more actions
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

  // The mobile sheet: the design's entries, then what the desktop bar keeps in its own
  // menus, since this is the only menu below lg. Preview is absent - it is the eye button.
  const viewEntry = (slug: RecipeView): SheetEntry[] => {
    const view = views.find((v) => v.slug === slug);
    if (!view) return [];
    return [
      {
        key: `--sheet-view-${view.slug}`,
        label: view.label,
        iconHtml: view.icon,
        onPick: () => showView(view.slug as RecipeView),
      },
    ];
  };

  // Whichever of Edit and Preview the header does not already reach in one tap.
  const otherWorkView: RecipeView =
    !atRoot && selectedView === "edit" ? "preview" : "edit";

  const sheetEntries: SheetEntry[] = view_only
    ? [
        // A visitor owns nothing here, so only read / inspect / remix are offered.
        ...views.map((view) => ({
          key: `--sheet-view-${view.slug}`,
          label: view.label,
          iconHtml: view.icon,
          onPick: () => showView(view.slug as RecipeView),
        })),
        ...(builder_event_key
          ? [
              {
                key: "--sheet-remix",
                label: "Remix",
                iconClass: "fa-regular fa-shuffle",
                // Opens Ask Gooey, where a workflow of their own starts.
                onPick: () => setBuilder(true),
              },
            ]
          : []),
      ]
    : [
        // Placed by name, since the design's order is not the view selector's.
        ...viewEntry("about"),
        // Only while Ask Gooey is on screen - it acts on the chat.
        ...(builder_new_event && atRoot
          ? [
              {
                key: "--sheet-new-chat",
                label: "New Chat",
                iconClass: "fa-regular fa-pen-to-square",
                onPick: () =>
                  window.dispatchEvent(new CustomEvent(builder_new_event)),
              },
            ]
          : []),
        ...viewEntry(otherWorkView),
        ...(history_href
          ? [
              {
                key: "--sheet-history",
                label: "Version History",
                iconClass: "fa-regular fa-clock-rotate-left",
                href: history_href,
                onPick: () => setBuilder(false),
              },
            ]
          : []),
        // Update is dropped - it already has a button in the header at this width.
        ...overflowEntries
          .filter((item) => item.key !== PUBLISH_ITEM_KEY)
          .map((item) => ({
            key: item.key,
            label: item.label,
            iconHtml: item.icon,
            href: item.href ?? undefined,
            heading: item.heading,
            // A link only needs to put Ask Gooey away before it navigates.
            onPick: item.href
              ? () => setBuilder(false)
              : () => pickMenuItem(item),
          })),
      ];

  const pickMenuItem = (item: TopBarMenuItem) => {
    setTitleMenuOpen(false);
    setOverflowOpen(false);
    setPublishMenuOpen(false);
    // the component's own entries, so they go straight to their keys
    if (item.key === PUBLISH_ITEM_KEY) return fire(publish_key);
    if (item.key === SHARE_ITEM_KEY) {
      if (share_key) return fire(share_key);
      return copyShareUrl();
    }
    fire(menu_key, item.key);
  };

  return (
    <div
      className={clsx(
        "gooey-topbar",
        // a level down the mobile stack, which the design gives a shorter bar and a softer rule
        !atRoot && "gooey-topbar-stacked"
      )}
    >
      <div className="gooey-topbar-left">
        {/* The way back below lg: the nav drawer at the root, the previous level elsewhere. */}
        <button
          type="button"
          className="gooey-topbar-nav d-lg-none"
          onClick={atRoot ? openNavDrawer : goBack}
          title={atRoot ? "Open menu" : "Back"}
          aria-label={atRoot ? "Open menu" : "Back"}
        >
          <i
            className={
              atRoot ? "fa-regular fa-bars" : "fa-regular fa-chevron-left"
            }
          />
        </button>

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
            {/* Which level of the stack is on screen; above lg the active pill says so. */}
            {!atRoot && !!crumb && (
              <span className="gooey-topbar-crumb d-lg-none">
                <i
                  className="fa-regular fa-chevron-right gooey-topbar-crumb-sep"
                  aria-hidden="true"
                />
                {crumb}
              </span>
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
      </div>

      {/* A single-view recipe does not need a selector. */}
      {views.length > 1 && (
        <div
          className="gooey-topbar-tabs"
          style={{ visibility: paneVisibility(hydrated) }}
        >
          {views.map((view) => (
            <button
              type="button"
              key={view.slug}
              className={clsx(
                "gooey-topbar-tab",
                view.slug === activeViewSpec?.slug && "gooey-topbar-tab-active",
                view.desktop_only && "gooey-topbar-tab-desktop-only"
              )}
              onClick={() => chooseView(view.slug as RecipeView)}
              // no title: they carry a visible label. `aria-pressed` conveys that these
              // change the workspace layout rather
              // than navigate to another page.
              aria-pressed={view.slug === activeViewSpec?.slug}
            >
              <Icon html={view.icon} className="gooey-topbar-tab-icon" />
              {view.label}
            </button>
          ))}
        </div>
      )}

      <div className="gooey-topbar-right">
        {/* Below lg only these two render; the desktop cluster is hidden by CSS, and cost
            and Run return as the editor's own bottom bar. */}
        {!!sheetEntries.length && (
          <button
            type="button"
            className="gooey-topbar-menu-btn d-lg-none"
            onClick={() => setSheetOpen(true)}
            title="More actions"
            aria-label="More actions"
            aria-haspopup="menu"
            aria-expanded={sheetOpen}
          >
            <i className="fa-solid fa-ellipsis-vertical" />
          </button>
        )}

        {/* Preview at the root, Update below it. The sheet never lists Preview, so this is
            the only way to reach it. */}
        {atRoot
          ? previewable && (
              <button
                type="button"
                className="gooey-topbar-action d-lg-none"
                onClick={() => showView("preview")}
                title="Preview"
                aria-label="Preview"
              >
                <i className="fa-regular fa-eye" />
              </button>
            )
          : !!publish_label && (
              <button
                type="button"
                className="gooey-topbar-action d-lg-none"
                onClick={() => fire(publish_key)}
                title={
                  has_unpublished_changes
                    ? `${publish_label} (unpublished changes)`
                    : publish_label
                }
                aria-label={publish_label}
              >
                <i className="fa-regular fa-floppy-disk" />
                {has_unpublished_changes && (
                  <span
                    className="gooey-topbar-dot"
                    title="Unpublished changes"
                  />
                )}
              </button>
            )}

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

        {/* At most one chip is labelled, none past two: the centred pill group leaves the
            right cluster half the bar's slack. Unlabelled chips keep their name in the
            tooltip and in the ... menu. */}
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

        {/* One control holding Update and Share. Hidden below lg, where both live in the
            ... menu instead. */}
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
                <span
                  className="gooey-topbar-dot"
                  title="Unpublished changes"
                />
              )}
            </button>
            <Menu
              items={publishEntries}
              open={publishMenuOpen}
              onPick={pickMenuItem}
            />
          </div>
        )}

        {/* The tooltip names the price and appends any per-recipe note; a bare "$0.05"
            read aloud in a row of controls means nothing. */}
        {!!cost_label &&
          (() => {
            const costName = `Run cost: ${cost_label}`;
            const costTip = cost_title
              ? `${costName} (${cost_title})`
              : costName;
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
            onClick={handleRun}
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

      {/* The editor's bottom bar, below lg only - above it cost and Run sit in the right
          cluster. Scoped to the editor, the one view with something to submit; Preview and
          Ask Gooey both put a composer at this edge. `!atRoot` as well as the view, since
          Ask Gooey covers the workspace without changing which view is selected behind it. */}
      {!atRoot && selectedView === "edit" && (!!cost_label || !!run_key) && (
        <div className="gooey-topbar-runbar d-lg-none">
          {!!cost_label &&
            (() => {
              const costName = `Run cost: ${cost_label}`;
              const costTip = cost_title
                ? `${costName} (${cost_title})`
                : costName;
              const inner = (
                <>
                  <span className="gooey-topbar-runbar-est">Est.</span>
                  {cost_label}
                </>
              );
              return cost_href ? (
                <a
                  className="gooey-topbar-runbar-cost"
                  href={cost_href}
                  title={costTip}
                  aria-label={costTip}
                >
                  {inner}
                </a>
              ) : (
                <span
                  className="gooey-topbar-runbar-cost"
                  title={costTip}
                  aria-label={costTip}
                >
                  {inner}
                </span>
              );
            })()}

          {!!run_key && (
            <button
              type="button"
              className={clsx(
                "gooey-topbar-runbar-run",
                is_running && "gooey-topbar-runbar-run-stop"
              )}
              disabled={run_disabled}
              onClick={handleRun}
              title={is_running ? "Stop this run" : run_label}
              aria-label={is_running ? "Stop this run" : run_label}
            >
              {is_running ? (
                <i className="fa-regular fa-xmark-large" />
              ) : (
                <i className="fa-solid fa-play" />
              )}
            </button>
          )}
        </div>
      )}

      {sheetOpen && (
        <MobileActionSheet
          entries={sheetEntries}
          onDismiss={() => setSheetOpen(false)}
        />
      )}
    </div>
  );
}

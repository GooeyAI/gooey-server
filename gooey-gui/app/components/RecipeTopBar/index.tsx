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
  viewport_wide_key,
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
  // the tick is the only feedback a copy gets, so it has to fall back to something rather
  // than leave the click looking like it did nothing
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
  // Mirrors the Builder panel's own state. Seeded from the server's copy, then kept in step by
  // the panel's `:changed` announcement - which is the authority, because a `:open` / `:close`
  // command can be dispatched before a listener exists, and the panel also restores itself
  // from storage without commanding anything at all.
  const [builderOpen, setBuilderOpen] = useState(
    Boolean(builder_event_key && state[builder_event_key])
  );
  const [titleMenuOpen, setTitleMenuOpen] = useState(false);
  const [overflowOpen, setOverflowOpen] = useState(false);
  const [publishMenuOpen, setPublishMenuOpen] = useState(false);
  const navigate = useNavigate();
  const { layout, hydrated, selectView } = usePaneLayout(
    storage_key,
    initial_view
  );
  // The shown layout, not the stored one - the bar must name the arrangement that is on
  // screen. A config pane holding the whole row makes that Edit even where a split is saved.
  const activeView = viewForLayout(shownLayout(layout, editor_full_width));
  const selectedView = selectedWorkspaceView(activeView, workspace_active);
  const activeViewSpec = views.find((view) => view.slug === selectedView);
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

  // Ask Gooey is where a workflow opens on a phone, so the panel is shown unasked - the design
  // has no way to close it, because there is nothing behind it to close back to.
  //
  // "Unasked" only until the user picks a view, which is what the stored pane layout records:
  // `usePaneLayout` writes it on every selection, so its absence means this session has not
  // chosen anything yet. Keying off that rather than a flag of our own keeps one fact in one
  // place, and stops the panel reopening over a pane the user just asked for.
  //
  // 1140px is the panel's own breakpoint (`--sidebar_desktop_breakpoint`), not lg: above it the
  // panel is a side rail that shares the screen, and opening it uninvited would take half the
  // window from whatever is already there.
  useEffect(() => {
    if (!builder_event_key) return;
    // Only on the workspace. On API or Deploy the panel is not this page's root - the editor
    // is, one level down - and opening it there would bury a page the user navigated to.
    if (!workspace_active) return;
    // A visitor lands on About, not on a chat: the first question is what this workflow is,
    // and Remix is how they opt into building one. Opening the panel over that answers a
    // question they have not asked yet.
    if (view_only) return;
    if (window.innerWidth >= 1140) return;
    let chosen: string | null = null;
    try {
      chosen = window.sessionStorage.getItem(storage_key);
    } catch {
      // Storage can be unavailable in private browsing; treat that as "nothing chosen yet",
      // which is the state a first visit is in anyway.
    }
    if (chosen) return;
    window.dispatchEvent(new CustomEvent(`${builder_event_key}:open`));
  }, [builder_event_key, storage_key]);

  // Below lg the bar is a navigation stack, not a set of tabs, and Ask Gooey is its root: the
  // panel covers the shell below the header, so while it is open there is no view on screen to
  // go back from - the left slot opens the nav drawer instead.
  //
  // Where there is no Builder at all there is no panel to be the root, so the entry view takes
  // the job. `initial_view` is the server's answer to "where does this workflow open", which
  // makes it the root by definition rather than a second guess at it.
  // A tab that is not the workspace is never the root: API and Deploy are levels above the
  // editor, so they always offer a way back, whatever the panel happens to be doing.
  //
  // Until the layout has hydrated, assume the root. Before then `layout` is whatever
  // `initial_view` says, and for an owner that is Split - so the crumb rendered "Split" for a
  // frame, until sessionStorage loaded, `keepLayoutOnScreen` folded Split away at this width,
  // and the panel announced itself. Naming a view the user never chose, and one that does not
  // exist on a phone, is worse than naming none: the root is the safe assumption, because
  // Ask Gooey is what a workflow opens on here. The pill group guards the same frame with
  // `paneVisibility(hydrated)`; this is that guard for the rest of the bar - it also keeps the
  // run bar from flashing in and the back arrow from appearing before there is a level to
  // leave.
  const atRoot =
    workspace_active &&
    (!hydrated ||
      (builder_event_key ? builderOpen : selectedView === initial_view));
  // What the crumb reads. The server names a non-workspace tab; on the workspace it is
  // whichever view is on screen.
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

  // Back out of a view. From API or Deploy that means leaving the tab for the workspace and
  // landing on Edit, which is the level they sit above - `chooseView` navigates on its own when
  // the workspace is not the current tab. On the workspace it is Ask Gooey where there is one,
  // and the entry view otherwise.
  const goBack = () => {
    if (!workspace_active) return chooseView("edit");
    if (builder_event_key) return setBuilder(true);
    chooseView(initial_view);
  };

  // Choosing a view from the sheet or the eye has to put Ask Gooey away, or the pane it
  // selects renders behind a panel that is covering the whole shell.
  const showView = (view: RecipeView) => {
    setBuilder(false);
    // Split is two columns, and there is room for one below lg - `keepLayoutOnScreen` folds it
    // to the preview alone. For "How it works", which is Split, that drops the configuration
    // the entry exists to show and lands on the bot instead, so the pick reads as opening the
    // wrong view and needing a second go. Ask for the editor directly at this width.
    const narrow = typeof window !== "undefined" && window.innerWidth < 992;
    chooseView(narrow && view === "split" ? "edit" : view);
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
  // Share sits in the Publish menu for both capabilities - opening the visibility dialog for
  // someone who can change it, copying the link for everyone else. The server sets exactly one
  // of the two, and neither on an unpublished run, which has no stable url to share.
  if (share_key || share_copy_url) {
    publishEntries.push({
      key: SHARE_ITEM_KEY,
      label: shareCopied ? "Link copied" : "Share",
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

  // Deploy is the fourth way to ship this workflow, beside saving, sharing and the API - and
  // like the API it is a route now rather than a pane, so it needs no key round-trip either.
  if (deploy_href) {
    publishEntries.push({
      key: DEPLOY_ITEM_KEY,
      label: "Deploy",
      icon: '<i class="fa-regular fa-rocket"></i>',
      href: deploy_href,
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

  // The mobile sheet. The design's five entries first, then whatever the desktop bar keeps in
  // its own menus - Publish, Share, API, the deployed channels. Those are appended rather than
  // dropped because the sheet is the *only* menu below lg: the design simply never drew a
  // workflow that had any of them. Preview is absent on purpose - it is the eye button.
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

  // The sheet carries whichever of Edit and Preview the header does not already reach in one
  // tap. At the root that is Edit, because the eye button is Preview; inside Edit it is Preview,
  // because the action button has become Update. Listing the view you are already looking at
  // was the alternative, and it is a row that does nothing.
  const otherWorkView: RecipeView =
    !atRoot && selectedView === "edit" ? "preview" : "edit";

  const sheetEntries: SheetEntry[] = view_only
    ? [
        // Read it, see how it is built, make your own. Everything else in this bar acts on a
        // run the visitor does not own, so none of it is offered rather than offered and
        // refused: no Update, no Share, no API, no Deploy, no version history.
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
                // Remix is not a save - there is nothing of the visitor's to save yet. It
                // opens Ask Gooey, which is where a workflow of their own starts.
                onPick: () => setBuilder(true),
              },
            ]
          : []),
      ]
    : [
        // Listed in the design's order, which is not the order the view selector uses - so each
        // entry is placed by name rather than swept up from `views`. Usage has no destination in
        // the app yet, so it is left out rather than rendered as a row that does nothing.
        ...viewEntry("about"),
        // Only while Ask Gooey is the surface on screen. A fresh thread is an action on the chat,
        // so offering it from Edit or Preview means starting one somewhere you cannot see it.
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
        // Update is dropped: it is the outlined button in the header on every view that has one,
        // and a menu row for the control sitting two inches above it is just a second way to miss.
        // Share, API and Deploy stay - they have no button of their own at this width.
        ...overflowEntries
          .filter((item) => item.key !== PUBLISH_ITEM_KEY)
          .map((item) => ({
            key: item.key,
            label: item.label,
            iconHtml: item.icon,
            href: item.href ?? undefined,
            heading: item.heading,
            // A link navigates, so its only job here is to put Ask Gooey away first -
            // otherwise the panel is still open when the next page mounts, on top of it.
            onPick: item.href
              ? () => setBuilder(false)
              : () => pickMenuItem(item),
          })),
      ];

  const pickMenuItem = (item: TopBarMenuItem) => {
    setTitleMenuOpen(false);
    setOverflowOpen(false);
    setPublishMenuOpen(false);
    // these two are the component's own entries, not server-declared menu items, so they
    // go straight to their keys instead of round-tripping through menu_key
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
        {/* The app's only header below lg, so it owns the way back: the drawer at the root of
            the stack, the previous level anywhere else. Above lg the rail is always on screen
            and the pills do the switching, so this has no job and is not rendered. */}
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
            {/* Which level of the stack is on screen, below lg only - above it the active
                pill already says so. Inside the title button rather than beside it: the two
                read as one heading, and the author line that shares this block is hidden at
                this width, so there is nothing else on the row to disturb. */}
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
                view.slug === selectedView && "gooey-topbar-tab-active",
                view.desktop_only && "gooey-topbar-tab-desktop-only"
              )}
              onClick={() => chooseView(view.slug as RecipeView)}
              // no title: these carry a visible label, so a tooltip repeating it is noise.
              // `aria-pressed` conveys that these controls change the workspace layout rather
              // than navigate to another page.
              aria-pressed={view.slug === selectedView}
            >
              <Icon html={view.icon} className="gooey-topbar-tab-icon" />
              {view.label}
            </button>
          ))}
        </div>
      )}

      <div className="gooey-topbar-right">
        {/* Two controls below lg, per the design: everything listable goes in the sheet, and
            the one action worth a tap of its own sits beside it. The desktop cluster below -
            chips, Publish, cost, Run - is hidden at this width by CSS; cost and Run come back
            as the editor's own bottom bar, which is where the design puts them. */}
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

        {/* Preview at the root of the stack, Update below it. ASSUMPTION: the design shows an
            eye on the Ask screens and a floppy on Preview/Edit, and Preview is the one pane
            the sheet never lists - so the eye is how you reach it. Flagged for review. */}
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

        {/* `cost_label` on its own is a bare price. The tooltip names what it is and appends
            any per-recipe note; the aria-label says it outright, since "$0.05" read aloud in
            a row of controls is meaningless. */}
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

      {/* The editor's bottom bar: what a run will cost on the left, the run itself on the
          right. Below lg only - above it both sit in this bar's right cluster.

          Scoped to the editor because that is the only view with anything to submit. The design
          gives Preview the bot's own composer at this edge and Ask Gooey the chat's, so a run
          bar there would be a second thing competing for the same strip of screen.

          `!atRoot` as well as the view, because the two are independent: Ask Gooey covers the
          workspace without changing which view is selected behind it, so checking the view
          alone put this bar over the chat's composer whenever the editor was what you had left.

          Same `handleRun` as the desktop button rather than a second path to the server: this
          is the same action in a different place, and a run that lands on a different view
          depending on which control started it would be a bug waiting to happen. */}
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

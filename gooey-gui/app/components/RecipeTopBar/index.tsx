import "./RecipeTopBar.css";

import clsx from "clsx";
import { Fragment, useEffect, useRef, useState } from "react";
import type {
  LinkTarget,
  RecipeTopBarProps,
  SubmitTarget,
  TopBarMenuItem,
} from "@gooey-types/recipe_top_bar_props";
import type { WorkspaceView } from "@gooey-types/recipe_workspace_props";
import { Link, useNavigate } from "@remix-run/react";
import {
  useAppShellPanel,
  useNavDrawer,
  useWorkspaceLayout,
} from "~/appShellContext";
import type { CustomComponentProps } from "~/components";
import type { WorkspaceLayout } from "../RecipeWorkspace/paneState";
import {
  activeViewForLayouts,
  isRootLayout,
  layoutsEqual,
  paneVisibility,
  workspaceTargetForLayout,
} from "../RecipeWorkspace/paneState";
import { MobileActionSheet, type SheetEntry } from "./MobileActionSheet";
import { isIntegrationLabelled } from "./integrationChips";
import type { SheetSlot } from "./sheetSlots";
import { sheetAudience, sheetSlots } from "./sheetSlots";
import { encodeSubmitIntent } from "./submitIntent";

type TopBarTarget = LinkTarget | SubmitTarget;
type MenuEntry = {
  key: string;
  label: string;
  iconHtml?: string | null;
  target?: TopBarTarget;
  isDanger?: boolean;
  mobileOnly?: boolean;
  heading?: boolean;
  onPick?: () => void;
};

// The bot itself as a destination, for tab sets that do not name it as a view of their own.
// A visitor's does not: About and How it works each pair with the preview on a wide screen,
// so it never needed a pill. Below lg both fold to a single pane, and then the header's eye
// is the only route to the bot - hence a view here rather than a missing one.
const PREVIEW_VIEW: WorkspaceView = {
  key: "preview",
  label: "Preview",
  // The eye, same as `icons.preview` on the Preview tab an owner is given and same as the
  // header button beside it - one destination should not be drawn two ways.
  icon_html: '<i class="fa-solid fa-eye"></i>',
  layout: { kind: "single", surface: "preview" },
  desktop_only: false,
};

// `BasePage.MENU_*` - the keys Python stamps on the title-menu items, so the sheet can put
// them in its own order rather than taking the list as it comes.
const MENU_VERSION_HISTORY_KEY = "--menu-version-history";
const MENU_DUPLICATE_KEY = "--menu-duplicate";
const MENU_DELETE_KEY = "--menu-delete";

// Where a "Run of <name>" row lands: the published run's own About. There is no
// per-surface url to link to, so the layout rides along as navigation state, which the next
// page reads while it hydrates.
const ABOUT_LAYOUT: WorkspaceLayout = {
  kind: "split",
  primary: "about",
  secondary: "preview",
};

// the Publish menu's own entries, distinguishable from anything the server declares
const PUBLISH_ITEM_KEY = "--topbar-item-publish";
const SHARE_ITEM_KEY = "--topbar-item-share";
const API_ITEM_KEY = "--topbar-item-api";
const DEPLOY_ITEM_KEY = "--topbar-item-deploy";

export function RecipeTopBar({
  config,
  title,
  title_href,
  photo_url,
  circle_photo,
  author,
  parent,
  title_menu_items,
  integrations,
  submit_intent_key,
  publish_label,
  publish_intent,
  has_unpublished_changes,
  api_href,
  share,
  run_intent,
  cost_label,
  cost_href,
  cost_title,
  view_only,
  crumb_label,
  deploy_href,
  builder_panel_key,
  builder_new_event,
  usage_href,
  usage_active,
  state,
}: CustomComponentProps & RecipeTopBarProps) {
  const [shareCopied, setShareCopied] = useState(false);
  const copyShareUrl = () => {
    if (share.kind !== "copy") {
      return;
    }
    if (!navigator.clipboard) {
      window.prompt("Copy this link", share.url);
      return;
    }
    navigator.clipboard
      .writeText(share.url)
      .then(() => {
        setShareCopied(true);
        setTimeout(() => setShareCopied(false), 2000);
      })
      .catch(() => window.prompt("Copy this link", share.url));
  };

  const [sheetOpen, setSheetOpen] = useState(false);
  const builder = useAppShellPanel(
    builder_panel_key,
    Boolean(builder_panel_key && state[builder_panel_key]),
    builder_panel_key ? `${config.storage_key}:builder` : null
  );
  const [titleMenuOpen, setTitleMenuOpen] = useState(false);
  const [overflowOpen, setOverflowOpen] = useState(false);
  const [publishMenuOpen, setPublishMenuOpen] = useState(false);
  const navigate = useNavigate();
  const { layout, storedLayout, hydrated, isNarrow, selectLayout } =
    useWorkspaceLayout(config);
  const previewView =
    config.views.find((view) => view.key === "preview") ?? PREVIEW_VIEW;
  // Used wherever a layout has to be named. Not `config.views`, which is what the desktop
  // pill strip draws - the supplied Preview is reachable from the header and the sheet, both
  // of which are the narrow layout's, and a pill for it would be redundant beside them.
  const views =
    previewView === PREVIEW_VIEW
      ? [...config.views, PREVIEW_VIEW]
      : config.views;
  const activeViewSpec = activeViewForLayouts(
    views,
    layout,
    storedLayout,
    config.workspace_active
  );
  const chooseView = (view: WorkspaceView) => {
    selectLayout(view.layout);
    const target = workspaceTargetForLayout(
      config.workspace_active,
      config.workspace_href
    );
    if (target) {
      navigate(target);
    }
  };
  const handleRun = () => {
    if (config.workspace_active && run_intent?.kind === "run") {
      window.setTimeout(() => selectLayout(config.run_layout), 0);
    }
  };

  // Ask Gooey covers the workspace without changing which view is selected behind it, so it
  // is a level of the mobile stack in its own right. Only over the workspace: on API or
  // Deploy the panel is not shown at all, and Back there has to leave the tab.
  const builderOpen =
    !!builder_panel_key && config.workspace_active && builder.open;

  // The bottom of the mobile stack: the view the server opens the workspace on, as it is
  // *shown*. The fold maps a split onto one of its panes, so Preview chosen on its own and
  // the work split folded to Preview are the same screen. Comparing the stored layouts
  // instead called only one of them the root: Back out of the other swapped a layout the
  // fold then drew identically, so it read as doing nothing but dropping the back arrow.
  // Before hydration the root is the safe guess - it is the only state whose left control,
  // the drawer, is always right.
  const atRoot =
    config.workspace_active &&
    !builderOpen &&
    (!hydrated ||
      isRootLayout(
        layout,
        config.initial_layout,
        config.narrow_surface,
        isNarrow
      ));
  // Ask Gooey carries its own title pill, so the bar neither repeats it nor goes on naming
  // the view underneath the panel.
  const crumb = builderOpen ? "" : crumb_label || activeViewSpec?.label || "";
  // The two surfaces that talk *about* the bot rather than being it, so from either the eye
  // is the way to it. Not on the work views: Edit pairs with the preview on a wide screen and
  // swaps to it from the sheet, and Preview is already there - the slot gives way to Update.
  const canShowPreview = builderOpen || activeViewSpec?.key === "about";
  const { setOpen: setNavDrawerOpen } = useNavDrawer();
  // Absent on a tab that carries no run control, where nothing is running as far as the
  // bar is concerned.
  const isRunning = run_intent?.kind === "stop";

  const setBuilder = (open: boolean) => {
    if (builder_panel_key) {
      builder.setOpen(open);
    }
  };

  const goBack = () => {
    // Ask Gooey sits over a view rather than replacing it, so closing it uncovers whatever
    // was behind and that is already the level below.
    if (builderOpen) {
      setBuilder(false);
      return;
    }
    const initialView = views.find((view) =>
      layoutsEqual(view.layout, config.initial_layout)
    );
    if (initialView) {
      showView(initialView);
    }
  };

  const showView = (view: WorkspaceView) => {
    setBuilder(false);
    chooseView(view);
  };

  const showBuilder = () => {
    setBuilder(true);
    // Usage is a page rather than a pane and does not draw the panel, so it has to be left
    // behind first. The panel is commanded open before the navigation and stays open across
    // it, so it is up when the workspace arrives.
    const target = workspaceTargetForLayout(
      config.workspace_active,
      config.workspace_href
    );
    if (target) {
      navigate(target);
    }
  };

  const titleMenuRef = useDismissOnOutsideClick(() => setTitleMenuOpen(false));
  const overflowRef = useDismissOnOutsideClick(() => setOverflowOpen(false));
  const publishMenuRef = useDismissOnOutsideClick(() =>
    setPublishMenuOpen(false)
  );

  const publishEntries: MenuEntry[] = [];
  if (publish_label && publish_intent) {
    publishEntries.push({
      key: PUBLISH_ITEM_KEY,
      label: publish_label,
      iconHtml: '<i class="fa-regular fa-floppy-disk"></i>',
      target: { kind: "submit", intent: publish_intent },
    });
  }
  if (share.kind !== "none") {
    publishEntries.push({
      key: SHARE_ITEM_KEY,
      label: shareCopied ? "Link copied" : "Share",
      iconHtml: share.icon_html,
      target:
        share.kind === "manage"
          ? { kind: "submit", intent: share.intent }
          : undefined,
      onPick: share.kind === "copy" ? copyShareUrl : undefined,
    });
  }
  if (api_href) {
    publishEntries.push({
      key: API_ITEM_KEY,
      label: "API",
      iconHtml: '<i class="fa-regular fa-code"></i>',
      target: { kind: "link", href: api_href },
    });
  }

  if (deploy_href) {
    publishEntries.push({
      key: DEPLOY_ITEM_KEY,
      label: "Deploy",
      iconHtml: '<i class="fa-regular fa-rocket"></i>',
      target: { kind: "link", href: deploy_href },
    });
  }

  const titleEntries = title_menu_items.map(menuEntryFromTopBarItem);
  const overflowEntries: MenuEntry[] = [
    ...publishEntries.map((it) => ({ ...it, mobileOnly: true })),
    ...(integrations.length
      ? [
          {
            key: "--topbar-heading-deployments",
            label: "Deployments",
            mobileOnly: true,
            heading: true,
          },
        ]
      : []),
    ...integrations.map((it) => ({
      key: it.key,
      label: it.label,
      iconHtml: it.icon_html,
      target: it.target,
      mobileOnly: true,
    })),
  ];
  const viewEntry = (key: string, label?: string): SheetEntry[] => {
    const view = views.find((candidate) => candidate.key === key);
    // The sheet only exists below lg, so a view that asks to be desktop-only has no
    // business in it - Split is one, and it is why this guard is here rather than assumed.
    if (!view || view.desktop_only) {
      return [];
    }
    return [
      {
        key: `--sheet-view-${view.key}`,
        // The sheet names a couple of the surfaces differently from the desktop pills, which
        // have the room to be terser - so the label is overridable here.
        label: label ?? view.label,
        iconHtml: view.icon_html ?? undefined,
        onPick: () => showView(view),
      },
    ];
  };

  // Usage is a page, not a pane, so it is a link rather than a view - but it belongs in the
  // same list the panes do. Hidden while you are already looking at it.
  const usageEntry: SheetEntry[] =
    usage_href && !usage_active
      ? [
          {
            key: "--sheet-usage",
            label: "Usage",
            iconClass: "fa-regular fa-chart-line",
            href: usage_href,
            onPick: () => setBuilder(false),
          },
        ]
      : [];

  // The way into Ask Gooey. Not while the panel is already up, where the sheet offers New
  // Chat instead. What it offers to do depends on whose published run it is: your own is
  // edited, someone else's is remixed into a copy, and a saved run is just worked on.
  const builderEntry = (label: string): SheetEntry[] =>
    !builderOpen && !!builder_panel_key
      ? [
          {
            key: "--sheet-builder",
            label,
            iconClass: "fa-regular fa-sparkles",
            onPick: showBuilder,
          },
        ]
      : [];

  // A control on the Ask Gooey panel, so it is only offered while that panel is up.
  const newChatEntry: SheetEntry[] =
    builder_new_event && builderOpen
      ? [
          {
            key: "--sheet-new-chat",
            label: "New Chat",
            iconClass: "fa-regular fa-pen-to-square",
            onPick: () =>
              window.dispatchEvent(new CustomEvent(builder_new_event)),
          },
        ]
      : [];

  // The channels this published run is deployed to, as rows of their own. No group heading:
  // the menu is one flat list, and with a channel or two at the top of it a heading is more
  // furniture than help.
  const integrationEntries: SheetEntry[] = integrations.map((it) => ({
    key: it.key,
    label: it.label,
    iconHtml: it.icon_html,
    href: it.target.kind === "link" ? it.target.href : undefined,
    submitIntent: it.target.kind === "submit" ? it.target.intent : undefined,
    onPick: () => setBuilder(false),
  }));

  const sheetEntry = (entries: MenuEntry[], key: string): SheetEntry[] =>
    entries
      .filter((item) => item.key === key)
      .map((item) => ({
        key: item.key,
        label: item.label,
        iconHtml: item.iconHtml ?? undefined,
        href: item.target?.kind === "link" ? item.target.href : undefined,
        submitIntent:
          item.target?.kind === "submit" ? item.target.intent : undefined,
        onPick: item.onPick ?? (() => setBuilder(false)),
      }));

  // Named so the three menus below read as the orders they are, rather than as index
  // arithmetic over `publishEntries` and `title_menu_items`.
  const saveEntry = sheetEntry(publishEntries, PUBLISH_ITEM_KEY);
  const shareEntry = sheetEntry(publishEntries, SHARE_ITEM_KEY);
  const apiEntry = sheetEntry(publishEntries, API_ITEM_KEY);
  const deployEntry = sheetEntry(publishEntries, DEPLOY_ITEM_KEY);
  const versionsEntry = sheetEntry(titleEntries, MENU_VERSION_HISTORY_KEY);
  const duplicateEntry = sheetEntry(titleEntries, MENU_DUPLICATE_KEY);
  const deleteEntry = sheetEntry(titleEntries, MENU_DELETE_KEY);

  // Where a saved run's menu leads: back to the published run it belongs to, opening on
  // About. The layout rides along in the navigation state, read while the next page
  // hydrates.
  const parentEntry: SheetEntry[] = parent
    ? [
        {
          key: "--sheet-parent",
          label: `Run of ${parent.label}`,
          iconClass: "fa-regular fa-circle-info",
          href: parent.href,
          navigationLayout: ABOUT_LAYOUT,
          onPick: () => setBuilder(false),
        },
      ]
    : [];

  const audience = sheetAudience({ onSavedRun: !!parent, viewOnly: view_only });

  /* Every row the sheet can hold. `sheetSlots` picks which of them appear and in what order;
     the labels are here because they are the one thing that varies with who is looking - a
     visitor configures nothing, so their row explains rather than edits, and Ask Gooey
     edits your own published run, remixes someone else's and just works on a saved run. */
  const slotEntries: Record<SheetSlot, SheetEntry[]> = {
    parent: parentEntry,
    integrations: integrationEntries,
    about: viewEntry("about"),
    preview: viewEntry("preview"),
    edit:
      audience === "visitor"
        ? viewEntry("how-it-works", "How it Works")
        : viewEntry("edit"),
    newChat: newChatEntry,
    builder: builderEntry(
      {
        savedRun: "Ask Gooey",
        visitor: "Ask Gooey to Remix",
        editor: "Ask Gooey to Edit",
      }[audience]
    ),
    usage: usageEntry,
    save: saveEntry,
    deploy: deployEntry,
    share: shareEntry,
    api: apiEntry,
    versions: versionsEntry,
    duplicate: duplicateEntry,
    delete: deleteEntry,
  };

  const sheetEntries: SheetEntry[] = sheetSlots(audience).flatMap(
    (slot) => slotEntries[slot]
  );

  // Shared by the two forms the heading takes. The crumb sits inside it so a long name
  // ellipsises against it rather than pushing it off the row.
  const titleContent = (
    <>
      <span className="gooey-topbar-title-text">{title}</span>
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
    </>
  );

  const closeMenus = () => {
    setTitleMenuOpen(false);
    setOverflowOpen(false);
    setPublishMenuOpen(false);
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
          onClick={atRoot ? () => setNavDrawerOpen(true) : goBack}
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
          <div className="gooey-topbar-titlerow">
            {/* A heading that names another page is a link to it - a run points at the
                workflow it came from. Where it names this page the server sends no href and
                it stays the menu's trigger, as it is on the workflow's own url. */}
            {title_href ? (
              <Link
                to={title_href}
                className="gooey-topbar-title gooey-topbar-title-link"
                title={title}
              >
                {titleContent}
              </Link>
            ) : (
              <button
                type="button"
                className="gooey-topbar-title"
                onClick={() => setTitleMenuOpen((v) => !v)}
                disabled={!title_menu_items.length || isNarrow}
              >
                {titleContent}
                {!!title_menu_items.length && !isNarrow && (
                  <i className="fa-regular fa-chevron-down gooey-topbar-chevron" />
                )}
              </button>
            )}
            {/* Above lg the chevron is the only way to Versions, Duplicate and Delete, so
                once the title itself navigates the menu needs a trigger of its own. */}
            {!!title_href && !!title_menu_items.length && !isNarrow && (
              <button
                type="button"
                className="gooey-topbar-title-menu"
                onClick={() => setTitleMenuOpen((v) => !v)}
                title="Workflow options"
                aria-label="Workflow options"
                aria-haspopup="menu"
                aria-expanded={titleMenuOpen}
              >
                <i className="fa-regular fa-chevron-down gooey-topbar-chevron" />
              </button>
            )}
          </div>
          {author && (
            <span className="gooey-topbar-author">{author.label}</span>
          )}
          <Menu
            items={titleEntries}
            open={titleMenuOpen && !isNarrow}
            submitIntentKey={submit_intent_key}
            onDismiss={closeMenus}
          />
        </div>
      </div>

      {/* A single-view recipe does not need a selector unless Usage is available. */}
      {(config.views.length > 1 || !!usage_href) && (
        <div
          className="gooey-topbar-tabs"
          style={{ visibility: paneVisibility(hydrated) }}
        >
          {config.views.map((view) => (
            <button
              type="button"
              key={view.key}
              className={clsx(
                "gooey-topbar-tab",
                view.key === activeViewSpec?.key && "gooey-topbar-tab-active"
              )}
              onClick={() => chooseView(view)}
              aria-pressed={view.key === activeViewSpec?.key}
            >
              <Icon
                html={view.icon_html ?? undefined}
                className="gooey-topbar-tab-icon"
              />
              {view.label}
            </button>
          ))}
          {usage_href && (
            <Link
              to={usage_href}
              className={clsx(
                "gooey-topbar-tab",
                usage_active && "gooey-topbar-tab-active"
              )}
              onClick={() => setBuilder(false)}
              aria-current={usage_active ? "page" : undefined}
            >
              <i className="fa-regular fa-chart-line gooey-topbar-tab-icon" />
              Usage
            </Link>
          )}
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

        {/* Preview from About and from Ask Gooey, Update from the work views.

            `preventDefault` because the two share a slot: choosing Preview leaves About, so
            React patches this very node into the submit button below before the browser runs
            the click's activation behaviour, and the form was posting the publish intent -
            the save dialog opened on top of the preview. Cancelling the default action is
            immune to that ordering; re-keying the pair would not be. */}
        {canShowPreview ? (
          <button
            type="button"
            className="gooey-topbar-action d-lg-none"
            onClick={(e) => {
              e.preventDefault();
              showView(previewView);
            }}
            title="Preview"
            aria-label="Preview"
          >
            <i className="fa-regular fa-eye" />
          </button>
        ) : (
          !!publish_label &&
          !!publish_intent && (
            <button
              type="submit"
              name={submit_intent_key}
              value={encodeSubmitIntent(publish_intent)}
              className="gooey-topbar-action d-lg-none"
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
          )
        )}

        {!!overflowEntries.length && (
          <div className="gooey-topbar-overflow-wrap" ref={overflowRef}>
            <button
              type="button"
              className="gooey-topbar-overflow-btn d-lg-none"
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
              submitIntentKey={submit_intent_key}
              onDismiss={closeMenus}
            />
          </div>
        )}

        {/* Labels only in the view-only bar, and at most one there: the centred pill group
            leaves the right cluster half the bar's slack, and an editor's bar spends that on
            the tabs and Update. Unlabelled chips keep their name in the tooltip and in the
            ... menu. */}
        {integrations.map((integration, i) => {
          const labelled = isIntegrationLabelled({
            index: i,
            count: integrations.length,
            viewOnly: view_only,
          });
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
              <Icon html={integration.icon_html} />
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
          return integration.target.kind === "link" ? (
            <a
              key={integration.key}
              href={integration.target.href}
              className={className}
              style={style}
              title={integration.label}
              aria-label={integration.label}
            >
              {content}
            </a>
          ) : (
            <button
              key={integration.key}
              type="submit"
              name={submit_intent_key}
              value={encodeSubmitIntent(integration.target.intent)}
              className={className}
              style={style}
              title={integration.label}
              aria-label={integration.label}
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
              submitIntentKey={submit_intent_key}
              onDismiss={closeMenus}
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

        {!!cost_label && (
          <span className="gooey-topbar-sep" aria-hidden="true">
            /
          </span>
        )}

        {/* Omitted, not disabled, where the server sends no run intent: Usage lists the
            saved runs already made, so a Run control has nothing to do there. */}
        {!!run_intent && (
          <button
            type="submit"
            name={submit_intent_key}
            value={encodeSubmitIntent(run_intent)}
            className={clsx(
              "gooey-topbar-run",
              isRunning && "gooey-topbar-run-stop"
            )}
            onClick={handleRun}
            title={isRunning ? "Stop this run" : "Run"}
            aria-label={isRunning ? "Stop this run" : "Run"}
          >
            {isRunning ? (
              <i className="fa-regular fa-xmark-large" />
            ) : (
              <i className="fa-solid fa-play" />
            )}
            <span className="gooey-topbar-btn-label">
              {isRunning ? "Stop" : "Run"}
            </span>
          </button>
        )}
      </div>

      {sheetOpen && (
        <MobileActionSheet
          entries={sheetEntries}
          submitIntentKey={submit_intent_key}
          onDismiss={() => setSheetOpen(false)}
        />
      )}
    </div>
  );
}

function Menu({
  items,
  open,
  submitIntentKey,
  onDismiss,
}: {
  items: MenuEntry[];
  open: boolean;
  submitIntentKey: string;
  onDismiss: () => void;
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
        ) : item.target?.kind === "link" ? (
          <Link
            key={item.key}
            to={item.target.href}
            onClick={onDismiss}
            className={clsx(
              "gooey-topbar-menu-item",
              item.isDanger && "text-danger",
              item.mobileOnly && "d-lg-none"
            )}
          >
            <Icon
              html={item.iconHtml ?? undefined}
              className="gooey-topbar-menu-icon"
            />
            {item.label}
          </Link>
        ) : (
          <button
            key={item.key}
            type={item.target?.kind === "submit" ? "submit" : "button"}
            name={item.target?.kind === "submit" ? submitIntentKey : undefined}
            value={
              item.target?.kind === "submit"
                ? encodeSubmitIntent(item.target.intent)
                : undefined
            }
            className={clsx(
              "gooey-topbar-menu-item",
              item.isDanger && "text-danger",
              item.mobileOnly && "d-lg-none"
            )}
            onClick={() => {
              item.onPick?.();
              if (item.target?.kind !== "submit") {
                onDismiss();
              }
            }}
          >
            <Icon
              html={item.iconHtml ?? undefined}
              className="gooey-topbar-menu-icon"
            />
            {item.label}
          </button>
        )
      )}
    </div>
  );
}

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

function menuEntryFromTopBarItem(item: TopBarMenuItem): MenuEntry {
  return {
    key: item.key,
    label: item.label,
    iconHtml: item.icon_html,
    target: item.target,
    isDanger: item.is_danger,
  };
}

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
import { useCopyToClipboard } from "~/useCopyToClipboard";
import { GooeyTooltip } from "../GooeyTooltip";
import {
  activeViewForLayouts,
  isRootLayout,
  layoutsEqual,
  revealRunOutput,
  workspaceHrefToNavigate,
  workspaceLayoutNavigationState,
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
  /** Carries the unpublished-changes marker, so the row says what its button says. */
  dot?: boolean;
  heading?: boolean;
  onPick?: () => void;
};

// The bot itself as a destination, for tab sets that do not name it as a view of their own.
// A visitor's does not: About and How it works each pair with the preview on a wide screen,
// so it never needed a tab there. Below lg both fold to a single pane, and then the strip is
// the only route to the bot - hence a view here rather than a missing one.
const PREVIEW_VIEW: WorkspaceView = {
  key: "preview",
  label: "Preview",
  // Play, same as `icons.play` on the Preview tab an owner is given - one destination
  // should not be drawn two ways.
  icon_html: '<i class="fa-regular fa-play"></i>',
  layout: { kind: "single", surface: "preview" },
  desktop_only: false,
};

/** Whether About's own title has scrolled up behind the bar.
 *
 * Measured against the heading rather than a pixel threshold, so the bar takes the name over
 * exactly when the surface stops showing it. `scroll` does not bubble and the pane that
 * scrolls is not an ancestor of the bar, so this listens in the capture phase on `document`.
 * Inert unless `active`, which is what keeps it off the desktop.
 */
function useScrolledPastAboutTitle(active: boolean): boolean {
  const [past, setPast] = useState(false);
  useEffect(() => {
    if (!active) {
      setPast(false);
      return;
    }
    const read = () => {
      const heading = document.querySelector(".v2-about-heading");
      const bar = document.querySelector(".gooey-topbar");
      const box = heading?.getBoundingClientRect();
      if (!box || !bar) {
        setPast(false);
        return;
      }
      setPast(box.bottom <= bar.getBoundingClientRect().bottom);
    };
    // Read on the event rather than on a frame: rAF is throttled while the tab is not
    // painting, which left the bar naming the wrong thing on return - and two rects per
    // scroll event measured as no cost worth that.
    read();
    document.addEventListener("scroll", read, true);
    window.addEventListener("resize", read);
    return () => {
      document.removeEventListener("scroll", read, true);
      window.removeEventListener("resize", read);
    };
  }, [active]);
  return past;
}

// `BasePage.MENU_*` - the keys Python stamps on the title-menu items, so the sheet can put
// them in its own order rather than taking the list as it comes.
const MENU_VERSION_HISTORY_KEY = "--menu-version-history";
const MENU_DUPLICATE_KEY = "--menu-duplicate";
const MENU_DELETE_KEY = "--menu-delete";

// the Publish menu's own entries, distinguishable from anything the server declares
const PUBLISH_ITEM_KEY = "--topbar-item-publish";
const SHARE_ITEM_KEY = "--topbar-item-share";

// Where a "Run of <name>" row lands: the published run's own About. There is no per-surface
// url to link to, so the layout rides along as navigation state, which the next page reads
// while it hydrates.
const ABOUT_LAYOUT: WorkspaceLayout = {
  kind: "split",
  primary: "about",
  secondary: "preview",
};

/** The three ways a surface draws its icon: a bare class, server-supplied html, or a
 *  branded mark. At most one is set. */
type SurfaceIcon = {
  iconClass?: string;
  iconHtml?: string;
  iconUrl?: string;
};

/** A tab that is a route rather than a client-side pane: Usage, Deploy, API. */
type DocumentTab = {
  key: NonNullable<RecipeTopBarProps["active_document_tab"]>;
  label: string;
  iconClass: string;
  href: string;
  /** Deploy and API: reachable from the switcher, never a tab of their own. */
  switcherOnly?: boolean;
};

/** Which widths a tab is drawn at, as bootstrap display utilities.
 *
 * The strip is one element at every width, but the two ends of it differ by one tab each:
 * Split has nowhere to fold below lg, and the supplied Preview is only a destination there.
 * CSS rather than a viewport branch, so the markup is the same before and after hydration.
 */
function tabVisibility(
  view: WorkspaceView,
  declared: WorkspaceView[]
): string | undefined {
  if (view.desktop_only) return "d-none d-lg-inline-flex";
  if (!declared.some((it) => it.key === view.key)) return "d-lg-none";
  return undefined;
}

export function RecipeTopBar({
  config,
  title,
  title_href,
  logo_image_url,
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
  deploy_href,
  builder_panel_key,
  builder_storage_key,
  builder_new_event,
  builder_photo_url,
  usage_href,
  active_document_tab,
  state,
}: CustomComponentProps & RecipeTopBarProps) {
  const { copied: shareCopied, copyUrl } = useCopyToClipboard();
  const copyShareUrl = () => {
    if (share.kind !== "copy") {
      return;
    }
    copyUrl(share.url);
  };

  const builder = useAppShellPanel(
    builder_panel_key,
    Boolean(builder_panel_key && state[builder_panel_key]),
    // The server's key, not one built from the workspace's: the rail addresses this same
    // panel with the server's, and a key off `config.storage_key` moves with the published
    // run - so saving a workflow closed the panel that had asked for the save.
    builder_storage_key
  );
  const [switcherOpen, setSwitcherOpen] = useState(false);
  const [titleMenuOpen, setTitleMenuOpen] = useState(false);
  const [publishMenuOpen, setPublishMenuOpen] = useState(false);
  const navigate = useNavigate();
  const { layout, storedLayout, hydrated, isNarrow, selectLayout } =
    useWorkspaceLayout(config);
  // Every layout the bar can name, which is what the strip draws below lg. Wider than
  // `config.views` by the supplied Preview, which only the folded layout needs a tab for -
  // `tabVisibility` is what keeps it off the desktop strip.
  const views = config.views.some((view) => view.key === "preview")
    ? config.views
    : // Second, where an editor's own Preview tab sits - the design's order is About,
      // Preview, then the tab that edits, and a visitor's set should read the same.
      [config.views[0], PREVIEW_VIEW, ...config.views.slice(1)];
  // Routes rather than panes, so they navigate instead of selecting a layout and the server
  // says which is current. Only Usage is a tab; the other two are destinations the switcher
  // offers, and the pill names whichever of the three you are on.
  const documentTabs: DocumentTab[] = [
    usage_href && {
      key: "usage",
      label: "Usage",
      iconClass: "fa-regular fa-chart-line",
      href: usage_href,
    },
    deploy_href && {
      key: "deploy",
      label: "Deploy",
      iconClass: "fa-regular fa-rocket",
      href: deploy_href,
      switcherOnly: true,
    },
    api_href && {
      key: "api",
      label: "API",
      iconClass: "fa-regular fa-code",
      href: api_href,
      switcherOnly: true,
    },
  ].filter((tab): tab is DocumentTab => !!tab);
  const activeViewSpec = activeViewForLayouts(
    views,
    layout,
    storedLayout,
    config.workspace_active
  );
  const chooseView = (view: WorkspaceView) => {
    selectLayout(view.layout);
    const target = workspaceHrefToNavigate(
      config.workspace_active,
      config.workspace_href
    );
    if (target) {
      // Carry the pick. A document tab is a route, so leaving one is a real navigation, and
      // the workspace opens on the view its url asks for - which threw the `selectLayout`
      // above away and landed on About whichever view you had picked to leave by.
      navigate(target, { state: workspaceLayoutNavigationState(view.layout) });
    }
  };
  const handleRun = () => {
    if (config.workspace_active && run_intent?.kind === "run") {
      revealRunOutput(layout, config.run_layout, selectLayout);
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
  // About is the one surface with the strip, and the only one whose body names the workflow
  // itself - so it leads with the wordmark and keeps the strip below. Every other surface
  // collapses to a single row that names the workflow and carries the pill.
  const onAbout =
    !builderOpen && !active_document_tab && activeViewSpec?.key === "about";
  // About leads with the wordmark only while its own surface is still showing the name.
  // Scroll the name off and the bar takes it over, so the workflow is named exactly once.
  // Narrow only: above lg the bar names the workflow whatever the surface is doing. The
  // hook is called on every render - a `&&` in front of it would change the hook order.
  const scrolledPastAboutTitle = useScrolledPastAboutTitle(onAbout && isNarrow);
  const showsWordmark = onAbout && !scrolledPastAboutTitle;

  // The panel's own mark wherever it names itself, falling back to a glyph when the
  // deployment carries no branding.
  const builderIcon: SurfaceIcon = builder_photo_url
    ? { iconUrl: builder_photo_url }
    : { iconClass: "fa-regular fa-sparkles" };
  // What the pill says: the panel wins over the surface behind it, then a route names
  // itself, then the pane you are on.
  const surface: ({ label: string } & SurfaceIcon) | null =
    builderOpen
      ? { label: "Ask", ...builderIcon }
      : active_document_tab
        ? documentTabs.find((tab) => tab.key === active_document_tab) ?? null
        : activeViewSpec
          ? {
              label: activeViewSpec.label,
              iconHtml: activeViewSpec.icon_html ?? undefined,
            }
          : null;
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
    const target = workspaceHrefToNavigate(
      config.workspace_active,
      config.workspace_href
    );
    if (target) {
      navigate(target);
    }
  };

  const titleMenuRef = useDismissOnOutsideClick(
    () => setTitleMenuOpen(false),
    titleMenuOpen
  );
  const publishMenuRef = useDismissOnOutsideClick(
    () => setPublishMenuOpen(false),
    publishMenuOpen
  );

  const publishEntries: MenuEntry[] = [];
  if (publish_label && publish_intent) {
    publishEntries.push({
      key: PUBLISH_ITEM_KEY,
      label: publish_label,
      iconHtml: '<i class="fa-regular fa-floppy-disk"></i>',
      target: { kind: "submit", intent: publish_intent },
      dot: has_unpublished_changes,
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
  for (const tab of documentTabs) {
    if (tab.key === "usage") continue;
    publishEntries.push({
      key: `--topbar-item-${tab.key}`,
      label: tab.label,
      iconHtml: `<i class="${tab.iconClass}"></i>`,
      target: { kind: "link", href: tab.href },
    });
  }

  const titleEntries = title_menu_items.map(menuEntryFromTopBarItem);


  const viewEntry = (key: string, label?: string): SheetEntry[] => {
    const view = views.find((candidate) => candidate.key === key);
    // A view that asks to be desktop-only has no business here - Split is one. Nor does the
    // surface you are already on: the pill names it, and this is what the pill opens.
    if (!view || view.desktop_only) return [];
    if (
      view.key === activeViewSpec?.key &&
      !builderOpen &&
      !active_document_tab
    ) {
      return [];
    }
    return [
      {
        key: `--sheet-view-${view.key}`,
        // The sheet names a couple of the surfaces differently from the strip, which has
        // the room to be terser - so the label is overridable here.
        label: label ?? view.label,
        iconHtml: view.icon_html ?? undefined,
        onPick: () => showView(view),
      },
    ];
  };

  // The routes, from the list the strip draws Usage from, so a tab and its row cannot
  // disagree about where they lead. Hidden while you are already on one.
  const documentEntry = (key: DocumentTab["key"]): SheetEntry[] => {
    const tab = documentTabs.find((it) => it.key === key);
    if (!tab || tab.key === active_document_tab) return [];
    return [
      {
        key: `--sheet-${tab.key}`,
        label: tab.label,
        iconClass: tab.iconClass,
        href: tab.href,
        onPick: () => setBuilder(false),
      },
    ];
  };

  // The way into Ask Gooey. Not while the panel is already up, where New Chat takes this
  // row instead. What it offers depends on whose published run it is: your own is edited,
  // someone else's is remixed into a copy, and a saved run is just worked on.
  const builderEntry = (label: string): SheetEntry[] =>
    !builderOpen && !!builder_panel_key
      ? [{ key: "--sheet-builder", label, ...builderIcon, onPick: showBuilder }]
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
  // the menu is one flat list, and with a channel or two in it a heading is more furniture
  // than help.
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
    usage: documentEntry("usage"),
    save: sheetEntry(publishEntries, PUBLISH_ITEM_KEY),
    deploy: documentEntry("deploy"),
    share: sheetEntry(publishEntries, SHARE_ITEM_KEY),
    api: documentEntry("api"),
    versions: sheetEntry(titleEntries, MENU_VERSION_HISTORY_KEY),
    duplicate: sheetEntry(titleEntries, MENU_DUPLICATE_KEY),
    delete: sheetEntry(titleEntries, MENU_DELETE_KEY),
  };

  const switcherEntries: SheetEntry[] = sheetSlots(audience).flatMap(
    (slot) => slotEntries[slot]
  );

  // Shared by the two forms the heading takes.
  const titleContent = (
    <>
      <span className="gooey-topbar-title-text">{title}</span>
    </>
  );

  const closeMenus = () => {
    setTitleMenuOpen(false);
    setPublishMenuOpen(false);
  };

  return (
    <div
      className={clsx(
        "gooey-topbar",
        // the strip is on a row of its own here, which moves the bar's rule up above it
        onAbout && "gooey-topbar-with-strip",
        // a level down the mobile stack, which the design rules with the softer line
        !atRoot && "gooey-topbar-stacked"
      )}
    >
      {/* An agent with no JS never reaches hydration, so it is shown what was held back.
          Here rather than the app shell: this bar is the one part of v2 on every tab. */}
      <noscript
        dangerouslySetInnerHTML={{
          __html: "<style>.gooey-until-hydrated{visibility:visible}</style>",
        }}
      />

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

        {/* On About the bar says whose app this is rather than which workflow - the surface
            below names it - and hands the name over once that name scrolls away. Beside the
            drawer button rather than centred in the row, as drawn. */}
        {showsWordmark && !!logo_image_url && (
          <img
            src={logo_image_url}
            alt="Gooey.AI"
            className="gooey-topbar-logo d-lg-none"
          />
        )}

        {photo_url && (
          <img
            src={photo_url}
            alt=""
            className={clsx(
              "gooey-topbar-avatar",
              circle_photo && "gooey-topbar-avatar-circle",
              showsWordmark && "gooey-topbar-identity-hidden"
            )}
          />
        )}

        <div
          className={clsx(
            "gooey-topbar-titleblock",
            showsWordmark && "gooey-topbar-identity-hidden"
          )}
          ref={titleMenuRef}
        >
          <div className="gooey-topbar-titlerow">
            {/* The page's h1, around the control only: `h1` takes phrasing content, which
                `a` and `button` are and the row's `div` is not. */}
            <h1 className="gooey-topbar-heading">
              {/* A heading naming another page is a link to it; on its own url it stays
                  the menu's trigger, which is why the server sends no href there. */}
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
            </h1>
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

      {/* A single-view recipe does not need a selector unless a route tab joins it. Above lg
          the strip is the bar's own navigation on every surface; below lg it is About's, and
          the pill stands in for it everywhere else. */}
      {(config.views.length > 1 || !!documentTabs.length) && (
        <div
          className={clsx(
            "gooey-topbar-tabs",
            !onAbout && "d-none d-lg-flex",
            !hydrated && "gooey-until-hydrated"
          )}
        >
          {views.map((view) => (
            <GooeyTooltip
              key={view.key}
              content={view.label}
              placement="bottom"
              fitContent
            >
            <button
              type="button"
              className={clsx(
                "gooey-topbar-tab",
                view.key === activeViewSpec?.key && "gooey-topbar-tab-active",
                tabVisibility(view, config.views)
              )}
              onClick={() => chooseView(view)}
              aria-pressed={view.key === activeViewSpec?.key}
              aria-label={view.label}
            >
              <Icon
                html={view.icon_html ?? undefined}
                className="gooey-topbar-tab-icon"
              />
              <span className="gooey-topbar-tab-label">{view.label}</span>
            </button>
            </GooeyTooltip>
          ))}
          {documentTabs
            .filter((tab) => !tab.switcherOnly)
            .map((tab) => (
              <GooeyTooltip
                key={tab.key}
                content={tab.label}
                placement="bottom"
                fitContent
              >
              <Link
                to={tab.href}
                className={clsx(
                  "gooey-topbar-tab",
                  tab.key === active_document_tab && "gooey-topbar-tab-active"
                )}
                onClick={() => setBuilder(false)}
                aria-current={
                  tab.key === active_document_tab ? "page" : undefined
                }
                aria-label={tab.label}
              >
                <i className={clsx(tab.iconClass, "gooey-topbar-tab-icon")} />
                <span className="gooey-topbar-tab-label">{tab.label}</span>
              </Link>
              </GooeyTooltip>
            ))}
        </div>
      )}

      <div className="gooey-topbar-right">
        {/* The only control here below lg; the desktop cluster is hidden by CSS, and cost
            and Run return as the editor's own bottom bar.

            The way into Ask Gooey, which below lg is a level of the stack rather than a
            rail. Not while it is already up: Back is what closes it, and the panel's own
            header carries New Chat. */}
        {onAbout
          ? !!builder_panel_key && (
              <button
                type="button"
                className="gooey-topbar-askgooey d-lg-none"
                onClick={showBuilder}
                title="Ask Gooey"
                aria-label="Ask Gooey"
              >
                {builder_photo_url ? (
                  <img src={builder_photo_url} alt="" />
                ) : (
                  <i className="fa-regular fa-sparkles" />
                )}
              </button>
            )
          : !!surface && (
              <button
                type="button"
                className="gooey-topbar-viewpill d-lg-none"
                onClick={() => setSwitcherOpen(true)}
                title="Menu"
                aria-label={`Menu (currently ${surface.label})`}
                aria-haspopup="menu"
                aria-expanded={switcherOpen}
              >
                {surface.iconUrl ? (
                  <img
                    className="gooey-topbar-viewpill-mark"
                    src={surface.iconUrl}
                    alt=""
                  />
                ) : surface.iconHtml ? (
                  <span
                    className="gooey-topbar-viewpill-icon"
                    dangerouslySetInnerHTML={{ __html: surface.iconHtml }}
                  />
                ) : (
                  <i
                    className={clsx(
                      surface.iconClass,
                      "gooey-topbar-viewpill-icon"
                    )}
                  />
                )}
                <span className="gooey-topbar-viewpill-label">
                  {surface.label}
                </span>
                <i className="fa-regular fa-chevron-down" />
              </button>
            )}

        {/* Preview from About and from Ask Gooey, Update from the work views.

            Two different controls, so they carry distinct keys: without them React reuses
            one DOM node for both, and choosing Preview leaves About - so React patched this
            node into the submit button below before the browser ran the click's activation
            behaviour, and the form posted the publish intent. The save dialog opened on top
            of the preview. The keys keep the nodes apart; `preventDefault` stays as the
            direct guard on a control that must never submit. */}


        {/* Labels only in the view-only bar, and at most one there: the centred pill group
            leaves the right cluster half the bar's slack, and an editor's bar spends that on
            the tabs and Update. Unlabelled chips keep their name in the tooltip and in the
            tooltip. */}
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
          return (
            <GooeyTooltip
              key={integration.key}
              content={integration.label}
              placement="bottom"
              fitContent
            >
              {integration.target.kind === "link" ? (
                <a
                  href={integration.target.href}
                  className={className}
                  style={style}
                  aria-label={integration.label}
                >
                  {content}
                </a>
              ) : (
                <button
                  type="submit"
                  name={submit_intent_key}
                  value={encodeSubmitIntent(integration.target.intent)}
                  className={className}
                  style={style}
                  aria-label={integration.label}
                >
                  {content}
                </button>
              )}
            </GooeyTooltip>
          );
        })}

        {/* One control holding Update and Share. Hidden below lg, where both live in the
            ... menu instead. */}
        {!!publishEntries.length && (
          <div
            className="gooey-topbar-overflow-wrap d-none d-lg-block"
            ref={publishMenuRef}
          >
            <GooeyTooltip
              content={
                has_unpublished_changes
                  ? "Publish (unpublished changes)"
                  : "Publish"
              }
              placement="bottom"
              fitContent
            >
            <button
              type="button"
              className="gooey-topbar-publish"
              onClick={() => setPublishMenuOpen((v) => !v)}
              aria-label="Publish"
              aria-haspopup="menu"
              aria-expanded={publishMenuOpen}
            >
              <i className="fa-regular fa-floppy-disk" />
              <span className="gooey-topbar-btn-label">Publish</span>
              <i className="fa-regular fa-chevron-down gooey-topbar-chevron" />
              {has_unpublished_changes && <span className="gooey-topbar-dot" />}
            </button>
            </GooeyTooltip>
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
          <GooeyTooltip
            content={isRunning ? "Stop this run" : "Run"}
            placement="bottom"
            fitContent
          >
          <button
            type="submit"
            name={submit_intent_key}
            value={encodeSubmitIntent(run_intent)}
            className={clsx(
              "gooey-topbar-run",
              isRunning && "gooey-topbar-run-stop"
            )}
            onClick={handleRun}
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
          </GooeyTooltip>
        )}
      </div>

      {switcherOpen && (
        <MobileActionSheet
          entries={switcherEntries}
          submitIntentKey={submit_intent_key}
          onDismiss={() => setSwitcherOpen(false)}
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
    <div className="gooey-topbar-menu" role="menu">
      {items.map((item) =>
        item.heading ? (
          <div
            key={item.key}
            role="presentation"
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
            role="menuitem"
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
            {item.dot && <span className="gooey-topbar-menu-dot" />}
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
            role="menuitem"
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
            {item.dot && <span className="gooey-topbar-menu-dot" />}
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

/** Dismiss a menu on a click outside it or on Escape, and return focus to its trigger.
 *
 *  Only listens while the menu is open: `onDismiss` is an inline arrow at every call site,
 *  so listing it as a dependency re-bound two document listeners on every render of the
 *  bar - three menus' worth, most of them for menus that were shut. It is held in a ref
 *  instead, which is also what lets the effect depend on `open` alone. */
function useDismissOnOutsideClick(onDismiss: () => void, open: boolean) {
  const ref = useRef<HTMLDivElement>(null);
  const dismiss = useRef(onDismiss);
  dismiss.current = onDismiss;

  useEffect(() => {
    if (!open) return;
    const handleClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        dismiss.current();
      }
    };
    const handleKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      // Focus is inside the menu that is closing, so it has to be put somewhere the user
      // can carry on from - the trigger is the only thing that outlives the menu.
      const trigger = ref.current?.querySelector("button");
      dismiss.current();
      if (trigger instanceof HTMLElement) trigger.focus();
    };
    document.addEventListener("mousedown", handleClick);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handleClick);
      document.removeEventListener("keydown", handleKey);
    };
  }, [open]);

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


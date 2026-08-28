import "./RecipeTopBar.css";

import clsx from "clsx";
import { Fragment, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
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
import {
  activeViewForLayouts,
  layoutsEqual,
  paneVisibility,
  workspaceTargetForLayout,
} from "../RecipeWorkspace/paneState";
import { MobileActionSheet, type SheetEntry } from "./MobileActionSheet";
import { encodeSubmitIntent, type RecipeSubmitIntent } from "./submitIntent";

type TopBarTarget = LinkTarget | SubmitTarget;
type MenuEntry = {
  key: string;
  label: string;
  iconHtml?: string | null;
  target?: TopBarTarget;
  isDanger?: boolean;
  onPick?: () => void;
};

// the Publish menu's own entries, distinguishable from anything the server declares
const PUBLISH_ITEM_KEY = "--topbar-item-publish";
const SHARE_ITEM_KEY = "--topbar-item-share";
const API_ITEM_KEY = "--topbar-item-api";
const DEPLOY_ITEM_KEY = "--topbar-item-deploy";

export function RecipeTopBar({
  config,
  title,
  photo_url,
  circle_photo,
  author,
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
  history_href,
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
  const [publishMenuOpen, setPublishMenuOpen] = useState(false);
  const navigate = useNavigate();
  const {
    layout,
    storedLayout,
    hydrated,
    hadStoredLayout,
    isNarrow,
    selectLayout,
  } = useWorkspaceLayout(config);
  const activeViewSpec = activeViewForLayouts(
    config.views,
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
    if (config.workspace_active && run_intent.kind === "run") {
      window.setTimeout(() => selectLayout(config.run_layout), 0);
    }
  };

  useEffect(() => {
    if (!builder_panel_key || !config.workspace_active || view_only) {
      return;
    }
    if (window.innerWidth >= 992) {
      return;
    }
    if (!hadStoredLayout) {
      builder.setOpen(true);
    }
  }, [
    builder_panel_key,
    config.storage_key,
    config.workspace_active,
    hadStoredLayout,
    view_only,
  ]);

  const atRoot =
    config.workspace_active &&
    (!hydrated ||
      (builder_panel_key
        ? builder.open
        : layoutsEqual(storedLayout, config.initial_layout)));
  const crumb = crumb_label || activeViewSpec?.label || "";
  const previewView = config.views.find((view) => view.key === "preview");
  const editView = config.views.find((view) => view.key === "edit");
  const { setOpen: setNavDrawerOpen } = useNavDrawer();
  const isRunning = run_intent.kind === "stop";

  const setBuilder = (open: boolean) => {
    if (builder_panel_key) {
      builder.setOpen(open);
    }
  };
  const closeBuilder = () => setBuilder(false);

  const goBack = () => {
    if (!config.workspace_active) {
      setBuilder(false);
      if (editView) {
        chooseView(editView);
      }
      return;
    }
    if (builder_panel_key) {
      setBuilder(true);
      return;
    }
    const initialView = config.views.find((view) =>
      layoutsEqual(view.layout, config.initial_layout)
    );
    if (initialView) {
      chooseView(initialView);
    }
  };

  const showView = (view: WorkspaceView) => {
    setBuilder(false);
    chooseView(view);
  };

  const titleMenuRef = useDismissOnOutsideClick(() => setTitleMenuOpen(false));
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

  // Publish, Share, API, Deploy and the demo chips: everything the desktop bar shows as its
  // own control, which below lg the sheet has to carry instead.
  const deploymentEntries: SheetEntry[] = [
    ...publishEntries.map(sheetEntryFromMenuEntry),
    ...(integrations.length
      ? [
          {
            key: "--topbar-heading-deployments",
            label: "Deployments",
            heading: true,
          },
        ]
      : []),
    ...integrations.map((it) =>
      sheetEntryFromMenuEntry({
        key: it.key,
        label: it.label,
        iconHtml: it.icon_html,
        target: it.target,
      })
    ),
    // picking any of these leaves the workspace, so the Builder panel closes behind it
  ].map((entry) => ({ ...entry, onPick: entry.onPick ?? closeBuilder }));

  const sheetEntryForView = (view: WorkspaceView): SheetEntry => ({
    key: `--sheet-view-${view.key}`,
    label: view.label,
    iconHtml: view.icon_html ?? undefined,
    onPick: () => showView(view),
  });
  const viewEntry = (key: string): SheetEntry[] => {
    const view = config.views.find((candidate) => candidate.key === key);
    return view ? [sheetEntryForView(view)] : [];
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
            onPick: closeBuilder,
          },
        ]
      : [];

  const otherWorkView = activeViewSpec?.key === "edit" ? "preview" : "edit";

  const sheetEntries: SheetEntry[] = view_only
    ? [
        ...config.views
          .filter((view) => !view.desktop_only)
          .map(sheetEntryForView),
        ...usageEntry,
        ...(builder_panel_key
          ? [
              {
                key: "--sheet-remix",
                label: "Remix",
                iconClass: "fa-regular fa-shuffle",
                onPick: () => setBuilder(true),
              },
            ]
          : []),
      ]
    : [
        ...viewEntry("about"),
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
                label: "History",
                iconClass: "fa-regular fa-clock-rotate-left",
                href: history_href,
                onPick: closeBuilder,
              },
            ]
          : []),
        ...usageEntry,
        ...titleEntries.map(sheetEntryFromMenuEntry),
        // Publish is the bar's own control below lg, beside the ... button
        ...deploymentEntries.filter((item) => item.key !== PUBLISH_ITEM_KEY),
      ];

  const closeMenus = () => {
    setTitleMenuOpen(false);
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
          <button
            type="button"
            className="gooey-topbar-title"
            onClick={() => setTitleMenuOpen((v) => !v)}
            disabled={!title_menu_items.length || isNarrow}
          >
            <span className="gooey-topbar-title-text">{title}</span>
            {!!title_menu_items.length && !isNarrow && (
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
              onClick={closeBuilder}
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

        {/* Preview at the root, Update below it. The sheet never lists Preview, so this is
            the only way to reach it. */}
        {atRoot
          ? previewView && (
              <button
                type="button"
                className="gooey-topbar-action d-lg-none"
                onClick={() => showView(previewView)}
                title="Preview"
                aria-label="Preview"
              >
                <i className="fa-regular fa-eye" />
              </button>
            )
          : !!publish_label &&
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

        <CostReadout
          className="gooey-topbar-cost"
          label={cost_label}
          href={cost_href}
          note={cost_title}
        />

        {!!cost_label && (
          <span className="gooey-topbar-sep" aria-hidden="true">
            /
          </span>
        )}

        <RunButton
          className="gooey-topbar-run"
          stopClassName="gooey-topbar-run-stop"
          isRunning={isRunning}
          intent={run_intent}
          submitIntentKey={submit_intent_key}
          onClick={handleRun}
          showLabel
        />
      </div>

      {/* The editor's bottom bar, below lg only - above it cost and Run sit in the right
          cluster. Scoped to the editor, the one view with something to submit; Preview and
          Ask Gooey both put a composer at this edge. `!atRoot` as well as the view, since
          Ask Gooey covers the workspace without changing which view is selected behind it. */}
      {!atRoot && activeViewSpec?.key === "edit" && (
        <div className="gooey-topbar-runbar d-lg-none">
          <CostReadout
            className="gooey-topbar-runbar-cost"
            label={cost_label}
            href={cost_href}
            note={cost_title}
            prefix={<span className="gooey-topbar-runbar-est">Est.</span>}
          />

          <RunButton
            className="gooey-topbar-runbar-run"
            stopClassName="gooey-topbar-runbar-run-stop"
            isRunning={isRunning}
            intent={run_intent}
            submitIntentKey={submit_intent_key}
            onClick={handleRun}
          />
        </div>
      )}

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

/** The run price, as a link to the billing page when there is one to link to.
 *
 * The tooltip names the price and appends any per-recipe note: a bare "$0.05" read aloud in
 * a row of controls means nothing. */
function CostReadout({
  className,
  label,
  href,
  note,
  prefix,
}: {
  className: string;
  label?: string | null;
  href?: string | null;
  note?: string | null;
  prefix?: ReactNode;
}) {
  if (!label) return null;
  const name = `Run cost: ${label}`;
  const tip = note ? `${name} (${note})` : name;
  const content = (
    <>
      {prefix}
      {label}
    </>
  );
  return href ? (
    <a className={className} href={href} title={tip} aria-label={tip}>
      {content}
    </a>
  ) : (
    <span className={className} title={tip} aria-label={tip}>
      {content}
    </span>
  );
}

/** Run, or Stop while a run is in flight. Rendered twice - once in the bar's right cluster
 *  above lg, once in the editor's bottom bar below it - so the two cannot drift apart. */
function RunButton({
  className,
  stopClassName,
  isRunning,
  intent,
  submitIntentKey,
  onClick,
  showLabel = false,
}: {
  className: string;
  stopClassName: string;
  isRunning: boolean;
  intent: RecipeTopBarProps["run_intent"];
  submitIntentKey: string;
  onClick: () => void;
  showLabel?: boolean;
}) {
  const name = isRunning ? "Stop this run" : "Run";
  return (
    <button
      type="submit"
      name={submitIntentKey}
      value={encodeSubmitIntent(intent)}
      className={clsx(className, isRunning && stopClassName)}
      onClick={onClick}
      title={name}
      aria-label={name}
    >
      {isRunning ? (
        <i className="fa-regular fa-xmark-large" />
      ) : (
        <i className="fa-solid fa-play" />
      )}
      {showLabel && (
        <span className="gooey-topbar-btn-label">
          {isRunning ? "Stop" : "Run"}
        </span>
      )}
    </button>
  );
}

/** A dropdown under the title or the Publish button. Above lg only: below it the same
 *  actions are listed by `MobileActionSheet` instead. */
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
        item.target?.kind === "link" ? (
          <Link
            key={item.key}
            to={item.target.href}
            onClick={onDismiss}
            className={clsx(
              "gooey-topbar-menu-item",
              item.isDanger && "text-danger"
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
              item.isDanger && "text-danger"
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
  // Held in a ref so the listener is bound once. Callers pass an inline closure, which is a
  // new function every render, and depending on it directly would tear the listener down
  // and rebuild it on each one.
  const onDismissRef = useRef(onDismiss);
  onDismissRef.current = onDismiss;
  useEffect(() => {
    const handle = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        onDismissRef.current();
      }
    };
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, []);
  return ref;
}

function sheetEntryFromMenuEntry(item: MenuEntry): SheetEntry {
  return {
    key: item.key,
    label: item.label,
    iconHtml: item.iconHtml ?? undefined,
    href: item.target?.kind === "link" ? item.target.href : undefined,
    submitIntent:
      item.target?.kind === "submit" ? item.target.intent : undefined,
    onPick: item.onPick,
  };
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

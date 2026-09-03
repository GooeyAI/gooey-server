import "./RecipeWorkspace.css";

import clsx from "clsx";
import { createContext, useContext, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

import type { EditorRunBarProps } from "@gooey-types/recipe_top_bar_props";
import type {
  PageShellConfig,
  RecipeSurfaceProps,
  RecipeWorkspacePanesProps,
  RecipeWorkspaceProps,
  RecipeWorkspaceTriggerProps,
} from "@gooey-types/recipe_workspace_props";
import { useWorkspaceLayout } from "~/appShellContext";
import type { CustomComponentProps } from "~/components";
import { RenderedChildren } from "~/renderer";
import type { TreeNode } from "~/renderer";

import { encodeSubmitIntent } from "../RecipeTopBar/submitIntent";
import { LocalWorkspacePaneControl } from "../WorkspacePaneControl";
import {
  collapsePane,
  paneRolesForLayout,
  paneVisibility,
  workspaceControlsForLayout,
} from "./paneState";
import { namedSurfaceSlots } from "./surfaceSlots";

type RecipeWorkspaceContextValue = {
  config: PageShellConfig;
  activeEditorPane: string | null;
  setActiveEditorPane: (paneId: string) => void;
};
const RecipeWorkspaceContext =
  createContext<RecipeWorkspaceContextValue | null>(null);

export function RecipeWorkspace({
  children,
  onChange,
  state,
  config,
}: CustomComponentProps & RecipeWorkspaceProps) {
  const { layout, storedLayout, hydrated, selectLayout } =
    useWorkspaceLayout(config);
  const surfaces = namedSurfaceSlots(children);
  const roles = paneRolesForLayout(layout);
  const controls = workspaceControlsForLayout(layout);

  return (
    <RecipeWorkspaceProvider key={config.storage_key} config={config}>
      <div
        style={{ visibility: paneVisibility(hydrated) }}
        className="recipe-workspace container-xxl py-lg-2"
      >
        <WorkspacePane
          className="recipe-workspace-about"
          role={roles.about}
          node={surfaces.about}
          onChange={onChange}
          state={state}
        />
        <WorkspacePane
          className="recipe-workspace-editor"
          role={roles.editor}
          node={surfaces.editor}
          onChange={onChange}
          state={state}
          rightControls={
            <>
              {controls.closePreview && (
                <LocalWorkspacePaneControl
                  label="Close Preview"
                  icon={{
                    kind: "font_awesome",
                    class_name: "fa-regular fa-table-columns-merge-next",
                  }}
                  onClick={() =>
                    selectLayout(collapsePane(storedLayout, "preview"))
                  }
                />
              )}
              {controls.addPreview && (
                <LocalWorkspacePaneControl
                  label="Open Preview"
                  icon={{
                    kind: "font_awesome",
                    class_name: "fa-regular fa-table-columns-add-after",
                  }}
                  className="d-none d-lg-inline-flex"
                  onClick={() => selectLayout(config.run_layout)}
                />
              )}
            </>
          }
        />
        <WorkspacePane
          className="recipe-workspace-preview"
          role={roles.preview}
          node={surfaces.preview}
          onChange={onChange}
          state={state}
          leftControls={
            controls.addEditor && (
              <LocalWorkspacePaneControl
                label="Open Edit"
                icon={{
                  kind: "font_awesome",
                  class_name: "fa-regular fa-table-columns-add-before",
                }}
                className="d-none d-lg-inline-flex"
                onClick={() => selectLayout(config.run_layout)}
              />
            )
          }
        />
      </div>
    </RecipeWorkspaceProvider>
  );
}

function RecipeWorkspaceProvider({
  children,
  config,
}: {
  children: ReactNode;
  config: PageShellConfig;
}) {
  const [activeEditorPane, setActiveEditorPane] = useState<string | null>(null);
  return (
    <RecipeWorkspaceContext.Provider
      value={{ config, activeEditorPane, setActiveEditorPane }}
    >
      {children}
    </RecipeWorkspaceContext.Provider>
  );
}

export function RecipeWorkspacePanes({
  children,
  onChange,
  state,
  panes,
  className,
}: CustomComponentProps & RecipeWorkspacePanesProps & { className?: string }) {
  const { activeEditorPane, setActiveEditorPane } = useRecipeWorkspaceContext();
  const selectedPane = panes.some((pane) => pane.id === activeEditorPane)
    ? activeEditorPane
    : panes[0]?.id;
  if (panes.length !== children.length) {
    throw new Error("RecipeWorkspacePanes requires one child per pane");
  }
  return (
    <div className="d-flex flex-column h-100" style={{ minHeight: 0 }}>
      <div className={clsx(className, "mb-1")} role="tablist">
        {panes.map((pane) => {
          const selected = pane.id === selectedPane;
          return (
            <button
              key={pane.id}
              id={`editor-pane-tab-${pane.id}`}
              type="button"
              role="tab"
              className={selected ? "pane-active" : undefined}
              aria-selected={selected}
              aria-controls={`editor-pane-${pane.id}`}
              onClick={() => setActiveEditorPane(pane.id)}
            >
              {pane.label}
            </button>
          );
        })}
      </div>
      <div
        className="flex-grow-1 overflow-auto pt-2 pe-1 pe-lg-3"
        style={{ minHeight: 0 }}
      >
        {panes.map((pane, index) => (
          <div
            key={pane.id}
            id={`editor-pane-${pane.id}`}
            role="tabpanel"
            aria-labelledby={`editor-pane-tab-${pane.id}`}
            hidden={pane.id !== selectedPane}
          >
            <RenderedChildren
              children={[children[index]]}
              onChange={onChange}
              state={state}
            />
          </div>
        ))}
      </div>
    </div>
  );
}

export function RecipeWorkspaceTrigger({
  children,
  onChange,
  state,
  layout,
  editor_pane,
  className,
}: CustomComponentProps & RecipeWorkspaceTriggerProps) {
  const { config, setActiveEditorPane } = useRecipeWorkspaceContext();
  const { selectLayout } = useWorkspaceLayout(config);
  const handleClick = () => {
    selectLayout(layout);
    if (editor_pane) {
      setActiveEditorPane(editor_pane);
    }
  };
  return (
    <button
      type="button"
      className={className ?? undefined}
      onClick={handleClick}
    >
      <RenderedChildren children={children} onChange={onChange} state={state} />
    </button>
  );
}

export function RecipeSurface({
  children,
  onChange,
  state,
}: CustomComponentProps & RecipeSurfaceProps) {
  return (
    <RenderedChildren children={children} onChange={onChange} state={state} />
  );
}

/** Run, and the estimate, at the foot of the editor's column. Below lg only - above it the
 *  top bar's right cluster carries both, and two of each on one screen is one too many.
 *
 *  Rendered by Python as the last child of the editor surface, which is what scopes it to
 *  the editor: it is there whenever that pane is, without the top bar having to work out
 *  which view is on screen. */
export function EditorRunBar({
  submit_intent_key,
  run_intent,
  cost_label,
  cost_href,
  cost_title,
}: CustomComponentProps & EditorRunBarProps) {
  const { config } = useRecipeWorkspaceContext();
  const { selectLayout } = useWorkspaceLayout(config);
  const isRunning = run_intent.kind === "stop";
  const runLabel = isRunning ? "Stop this run" : "Run";
  // Show the output the moment a run starts, as the bar above does. A tick late, so the form
  // this button submits has posted before the layout moves under it.
  const handleRun = () => {
    if (run_intent.kind === "run") {
      window.setTimeout(() => selectLayout(config.run_layout), 0);
    }
  };
  return (
    <div className="v2-editor-runbar d-lg-none">
      {!!cost_label && (
        <CostReading label={cost_label} href={cost_href} title={cost_title} />
      )}
      <button
        type="submit"
        name={submit_intent_key}
        value={encodeSubmitIntent(run_intent)}
        className={clsx(
          "v2-editor-runbar-run",
          isRunning && "v2-editor-runbar-run-stop"
        )}
        onClick={handleRun}
        title={runLabel}
        aria-label={runLabel}
      >
        {isRunning ? (
          <i className="fa-regular fa-xmark-large" />
        ) : (
          <i className="fa-solid fa-play" />
        )}
      </button>
    </div>
  );
}

/** The estimate, as a link to top-ups where there is one. "Est." qualifies the number rather
 *  than being part of it, so it is left out of what gets read aloud. */
function CostReading({
  label,
  href,
  title,
}: {
  label: string;
  href: string | null;
  title: string | null;
}) {
  let tooltip = `Run cost: ${label}`;
  if (title) {
    tooltip = `${tooltip} (${title})`;
  }
  const inner = (
    <>
      <span className="v2-editor-runbar-est">Est.</span>
      {label}
    </>
  );
  if (href) {
    return (
      <a
        className="v2-editor-runbar-cost"
        href={href}
        title={tooltip}
        aria-label={tooltip}
      >
        {inner}
      </a>
    );
  }
  return (
    <span
      className="v2-editor-runbar-cost"
      title={tooltip}
      aria-label={tooltip}
    >
      {inner}
    </span>
  );
}

function WorkspacePane({
  className,
  role,
  node,
  onChange,
  state,
  leftControls,
  rightControls,
}: {
  className: string;
  role: "closed" | "solo" | "major" | "minor";
  node: TreeNode;
  onChange: CustomComponentProps["onChange"];
  state: CustomComponentProps["state"];
  leftControls?: ReactNode;
  rightControls?: ReactNode;
}) {
  const open = role !== "closed";
  const paneRef = useRef<HTMLElement>(null);
  useEffect(() => {
    if (open) {
      paneRef.current?.removeAttribute("inert");
      return;
    }
    paneRef.current?.setAttribute("inert", "");
  }, [open]);

  return (
    <section
      ref={paneRef}
      className={clsx(
        "recipe-workspace-pane",
        className,
        `recipe-workspace-pane--${role}`,
        open && "recipe-workspace-pane--open"
      )}
      aria-hidden={!open}
    >
      {leftControls && (
        <div className="recipe-workspace-controls recipe-workspace-controls--left">
          {leftControls}
        </div>
      )}
      {rightControls && (
        <div className="recipe-workspace-controls recipe-workspace-controls--right">
          {rightControls}
        </div>
      )}
      <div className="recipe-workspace-pane-content">
        <RenderedChildren
          children={node.children}
          onChange={onChange}
          state={state}
        />
      </div>
    </section>
  );
}

function useRecipeWorkspaceContext() {
  const value = useContext(RecipeWorkspaceContext);
  if (!value) {
    throw new Error(
      "RecipeWorkspaceContext must be used inside RecipeWorkspace"
    );
  }
  return value;
}

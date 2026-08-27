import "./RecipeWorkspace.css";

import clsx from "clsx";
import { createContext, useContext, useEffect, useRef } from "react";
import type { ReactNode } from "react";

import type {
  PageShellConfig,
  RecipeSurfaceProps,
  RecipeWorkspaceProps,
  RecipeWorkspaceTriggerProps,
  SurfaceId,
} from "@gooey-types/recipe_workspace_props";
import { useWorkspaceLayout } from "~/appShellContext";
import type { CustomComponentProps } from "~/components";
import { RenderedChildren } from "~/renderer";
import type { TreeNode } from "~/renderer";

import { LocalWorkspacePaneControl } from "../WorkspacePaneControl";
import {
  collapsePane,
  paneRolesForLayout,
  paneVisibility,
  workspaceControlsForLayout,
} from "./paneState";

const RecipeWorkspaceConfigContext = createContext<PageShellConfig | null>(
  null
);

export function RecipeWorkspace({
  children,
  onChange,
  state,
  config,
}: CustomComponentProps & RecipeWorkspaceProps) {
  const { layout, storedLayout, hydrated, selectLayout } =
    useWorkspaceLayout(config);
  const surfaces = namedSurfaces(children);
  const roles = paneRolesForLayout(layout);
  const controls = workspaceControlsForLayout(layout);

  return (
    <RecipeWorkspaceConfigContext.Provider value={config}>
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
    </RecipeWorkspaceConfigContext.Provider>
  );
}

export function RecipeWorkspaceTrigger({
  children,
  onChange,
  state,
  layout,
  state_update,
  className,
}: CustomComponentProps & RecipeWorkspaceTriggerProps) {
  const config = useRecipeWorkspaceConfig();
  const { selectLayout } = useWorkspaceLayout(config);
  const handleClick = () => {
    selectLayout(layout);
    if (state_update && state[state_update.key] !== state_update.value) {
      state[state_update.key] = state_update.value;
      onChange();
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

function namedSurfaces(children: TreeNode[]): Record<SurfaceId, TreeNode> {
  const surfaces = {} as Partial<Record<SurfaceId, TreeNode>>;
  for (const child of children) {
    if (child.name !== "RecipeSurface") {
      throw new Error(
        `RecipeWorkspace child must be RecipeSurface, got ${child.name}`
      );
    }
    const surface = child.props.surface as SurfaceId;
    if (surfaces[surface]) {
      throw new Error(`RecipeWorkspace received duplicate ${surface} surface`);
    }
    surfaces[surface] = child;
  }
  for (const surface of ["about", "editor", "preview"] as const) {
    if (!surfaces[surface]) {
      throw new Error(`RecipeWorkspace is missing ${surface} surface`);
    }
  }
  return surfaces as Record<SurfaceId, TreeNode>;
}

function useRecipeWorkspaceConfig(): PageShellConfig {
  const config = useContext(RecipeWorkspaceConfigContext);
  if (!config) {
    throw new Error("RecipeWorkspaceTrigger must be inside RecipeWorkspace");
  }
  return config;
}

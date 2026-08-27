import "./RecipeWorkspace.css";

import clsx from "clsx";

import { useEffect, useRef } from "react";
import type { ReactNode } from "react";
import type { CustomComponentProps } from "~/components";
import type {
  RecipeWorkspaceProps,
  RecipeWorkspaceTriggerProps,
} from "@gooey-types/recipe_workspace_props";
import { RenderedChildren } from "~/renderer";

import { WorkspacePaneControl } from "../WorkspacePaneControl";
import {
  type PaneRole,
  paneRolesForLayout,
  paneVisibility,
  shownLayout,
  workspaceControlsForLayout,
} from "./paneState";
import { usePaneLayout } from "./usePaneLayout";

export function RecipeWorkspace({
  children,
  onChange,
  state,
  storage_key,
  initial_view,
  editor_full_width,
  narrow_pane,
}: CustomComponentProps & RecipeWorkspaceProps) {
  const { layout, hydrated, selectView, collapse } = usePaneLayout(
    storage_key,
    initial_view,
    narrow_pane
  );
  const [aboutPane, editorPane, previewPane] = children;
  // Both come off the shown layout, so a control can never contradict what is on screen.
  const shown = shownLayout(layout, editor_full_width);
  const roles = paneRolesForLayout(shown);
  const controls = workspaceControlsForLayout(shown, editor_full_width);

  return (
    <div
      style={{ visibility: paneVisibility(hydrated) }}
      className="recipe-workspace container-xxl"
    >
      <WorkspacePane
        className="recipe-workspace-about"
        role={roles.about}
        node={aboutPane}
        onChange={onChange}
        state={state}
      />
      <WorkspacePane
        className="recipe-workspace-editor"
        role={roles.editor}
        node={editorPane}
        onChange={onChange}
        state={state}
        rightControls={
          <>
            {controls.mergePreview && (
              <WorkspacePaneControl
                label="Close Preview"
                icon="fa-regular fa-table-columns-merge-next"
                onClick={() => collapse("preview")}
              />
            )}
            {controls.addPreview && (
              <WorkspacePaneControl
                label="Open Preview"
                icon="fa-regular fa-table-columns-add-after"
                className="d-none d-lg-inline-flex"
                onClick={() => selectView("split")}
              />
            )}
          </>
        }
      />
      <WorkspacePane
        className="recipe-workspace-preview"
        role={roles.preview}
        node={previewPane}
        onChange={onChange}
        state={state}
        leftControls={
          controls.addEdit && (
            <WorkspacePaneControl
              label="Open Edit"
              icon="fa-regular fa-table-columns-add-before"
              className="d-none d-lg-inline-flex"
              onClick={() => selectView("split")}
            />
          )
        }
      />
    </div>
  );
}

export function RecipeWorkspaceTrigger({
  children,
  onChange,
  state,
  storage_key,
  initial_view,
  view,
  state_key,
  state_value,
  className,
}: CustomComponentProps & RecipeWorkspaceTriggerProps) {
  const { selectView } = usePaneLayout(storage_key, initial_view);
  const handleClick = () => {
    selectView(view);
    if (state_key && state[state_key] !== state_value) {
      state[state_key] = state_value;
      onChange();
    }
  };
  return (
    <button type="button" className={className} onClick={handleClick}>
      <RenderedChildren children={children} onChange={onChange} state={state} />
    </button>
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
  role: PaneRole;
  node: CustomComponentProps["children"][number] | undefined;
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
        {node && (
          <RenderedChildren
            children={node.children}
            onChange={onChange}
            state={state}
          />
        )}
      </div>
    </section>
  );
}

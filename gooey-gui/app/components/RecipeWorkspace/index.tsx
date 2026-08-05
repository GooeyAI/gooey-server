import "./RecipeWorkspace.css";

import clsx from "clsx";
import { useEffect, useRef } from "react";
import type { ReactNode } from "react";
import type { CustomComponentProps } from "~/components";
import { RenderedChildren } from "~/renderer";

import { WorkspacePaneControl } from "../WorkspacePaneControl";
import {
  paneVisibility,
  type RecipeView,
  workspaceControlsForLayout,
} from "./paneState";
import { usePaneLayout } from "./usePaneLayout";

export function RecipeWorkspace({
  children,
  onChange,
  state,
  storage_key,
  initial_view,
  show_preview_new_chat,
}: CustomComponentProps & {
  storage_key: string;
  initial_view: RecipeView;
  show_preview_new_chat: boolean;
}) {
  const { layout, hydrated, selectView, collapse } = usePaneLayout(
    storage_key,
    initial_view
  );
  const [aboutPane, editorPane, previewPane] = children;
  const aboutOpen = layout.mode === "about";
  const editorOpen = layout.mode === "work" && layout.editorOpen;
  const previewOpen =
    layout.previewOpen && (layout.mode === "about" || layout.mode === "work");
  const controls = workspaceControlsForLayout(layout, show_preview_new_chat);
  const startNewChat = () => {
    document.getElementById("onNewConversation")?.click();
  };

  return (
    <div
      style={{ visibility: paneVisibility(hydrated) }}
      className={clsx(
        "recipe-workspace",
        "container-xxl",
        aboutOpen && "recipe-workspace--about",
        editorOpen && "recipe-workspace--editor",
        previewOpen && "recipe-workspace--preview"
      )}
    >
      {layout.mode === "work" && !layout.editorOpen && layout.previewOpen && (
        <button
          type="button"
          className="recipe-workspace-mobile-back d-lg-none"
          onClick={() => selectView("edit")}
        >
          <i className="fa-regular fa-arrow-left" />
          Back
        </button>
      )}
      <WorkspacePane
        className="recipe-workspace-about"
        open={aboutOpen}
        node={aboutPane}
        onChange={onChange}
        state={state}
      />
      <WorkspacePane
        className="recipe-workspace-editor"
        open={editorOpen}
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
        open={previewOpen}
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
        rightControls={
          <>
            {controls.newChat && (
              <WorkspacePaneControl
                label="New chat"
                icon="fa-regular fa-plus"
                onClick={startNewChat}
              />
            )}
          </>
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
  state_key = "",
  state_value,
  className,
}: CustomComponentProps & {
  storage_key: string;
  initial_view: RecipeView;
  view: RecipeView;
  state_key?: string;
  state_value?: unknown;
  className?: string;
}) {
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
  open,
  node,
  onChange,
  state,
  leftControls,
  rightControls,
}: {
  className: string;
  open: boolean;
  node: CustomComponentProps["children"][number] | undefined;
  onChange: CustomComponentProps["onChange"];
  state: CustomComponentProps["state"];
  leftControls?: ReactNode;
  rightControls?: ReactNode;
}) {
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
        open ? "recipe-workspace-pane--open" : "recipe-workspace-pane--closed"
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

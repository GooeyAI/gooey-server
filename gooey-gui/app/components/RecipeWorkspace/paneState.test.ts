import { describe, expect, it } from "vitest";

import type { PageShellConfig } from "@gooey-types/recipe_workspace_props";
import {
  activeViewForLayouts,
  collapsePane,
  foldForNarrowViewport,
  initialWorkspaceState,
  isRootLayout,
  layoutsEqual,
  normalizeWorkspaceLayout,
  paneRolesForLayout,
  paneVisibility,
  revealRunLayout,
  singleLayout,
  splitLayout,
  workspaceControlsForLayout,
  workspaceLayoutFromNavigationState,
  workspaceLayoutNavigationState,
  workspaceTargetForLayout,
} from "./paneState";

const about = splitLayout("about", "preview");
const edit = singleLayout("editor");
const preview = singleLayout("preview");
const split = splitLayout("editor", "preview");

const baseConfig: PageShellConfig = {
  storage_key: "recipe-layout",
  initial_layout: about,
  run_layout: split,
  route_layout: null,
  views: [
    {
      key: "about",
      label: "About",
      icon_html: null,
      layout: about,
      desktop_only: false,
    },
    {
      key: "edit",
      label: "Edit",
      icon_html: null,
      layout: edit,
      desktop_only: false,
    },
    {
      key: "preview",
      label: "Preview",
      icon_html: null,
      layout: preview,
      desktop_only: false,
    },
    {
      key: "split",
      label: "Split",
      icon_html: null,
      layout: split,
      desktop_only: true,
    },
  ],
  narrow_surface: "preview",
  workspace_href: "/agent/",
  workspace_active: true,
  active_run_id: null,
};

describe("workspace layout", () => {
  it("models a single surface separately from a split arrangement", () => {
    expect(edit).toEqual({ kind: "single", surface: "editor" });
    expect(split).toEqual({
      kind: "split",
      primary: "editor",
      secondary: "preview",
    });
    expect(() => splitLayout("editor", "editor")).toThrow(
      "requires two different surfaces"
    );
  });

  it("compares discriminated layouts", () => {
    expect(layoutsEqual(split, { ...split })).toBe(true);
    expect(layoutsEqual(split, about)).toBe(false);
    expect(layoutsEqual(edit, preview)).toBe(false);
  });

  it("normalizes malformed and legacy stored layouts", () => {
    expect(normalizeWorkspaceLayout(null, about)).toEqual(about);
    expect(
      normalizeWorkspaceLayout(
        { mode: "work", editorOpen: true, previewOpen: false },
        about
      )
    ).toEqual(edit);
    expect(
      normalizeWorkspaceLayout(
        { mode: "about", editorOpen: true, previewOpen: true },
        edit
      )
    ).toEqual(about);
  });
});

describe("initialWorkspaceState", () => {
  it("reads a versioned stored layout", () => {
    const storage = {
      getItem: () =>
        JSON.stringify({ version: 1, layout: edit, handled_run_id: null }),
    };
    expect(initialWorkspaceState(baseConfig, storage, null)).toEqual({
      version: 1,
      layout: edit,
      handled_run_id: null,
    });
  });

  it("lets navigation layout override storage", () => {
    const storage = { getItem: () => JSON.stringify(edit) };
    const navigation = workspaceLayoutNavigationState(split);
    expect(
      initialWorkspaceState(baseConfig, storage, navigation).layout
    ).toEqual(split);
    expect(workspaceLayoutFromNavigationState(navigation)).toEqual(split);
  });

  it("makes the preview route authoritative", () => {
    const config = {
      ...baseConfig,
      route_layout: preview,
      active_run_id: "run-1",
    };
    const storage = { getItem: () => JSON.stringify(edit) };
    expect(initialWorkspaceState(config, storage, null)).toEqual({
      version: 1,
      layout: preview,
      handled_run_id: "run-1",
    });
  });

  it("reveals a newly running run once", () => {
    const config = { ...baseConfig, active_run_id: "run-1" };
    const storage = { getItem: () => JSON.stringify(edit) };
    const started = initialWorkspaceState(config, storage, null);
    expect(started).toEqual({
      version: 1,
      layout: split,
      handled_run_id: "run-1",
    });

    const closed = {
      ...started,
      layout: collapsePane(started.layout, "preview"),
    };
    expect(revealRunLayout(closed, config)).toEqual(closed);
  });
});

describe("responsive layout", () => {
  it("folds work splits to the configured surface", () => {
    expect(foldForNarrowViewport(split, "preview", true)).toEqual(preview);
    expect(foldForNarrowViewport(split, "editor", true)).toEqual(edit);
  });

  it("keeps About as the primary narrow surface", () => {
    expect(foldForNarrowViewport(about, "preview", true)).toEqual(
      singleLayout("about")
    );
  });

  it("leaves wide and single layouts unchanged", () => {
    expect(foldForNarrowViewport(split, "preview", false)).toEqual(split);
    expect(foldForNarrowViewport(edit, "preview", true)).toEqual(edit);
  });

  it("calls the root what the fold shows, not what is stored", () => {
    // The work split folds to Preview, so Preview chosen on its own is the same screen and
    // has to count as the root too - otherwise Back sits there offering to swap one for the
    // other, which the fold then draws identically.
    expect(isRootLayout(preview, split, "preview", true)).toBe(true);
    expect(isRootLayout(edit, split, "preview", true)).toBe(false);
    // Wide, the two are different arrangements again.
    expect(isRootLayout(preview, split, "preview", false)).toBe(false);
    expect(isRootLayout(split, split, "preview", false)).toBe(true);
  });
});

describe("pane roles and controls", () => {
  it("assigns roles from explicit surfaces", () => {
    expect(paneRolesForLayout(about)).toEqual({
      about: "major",
      editor: "closed",
      preview: "minor",
    });
    expect(paneRolesForLayout(edit)).toEqual({
      about: "closed",
      editor: "solo",
      preview: "closed",
    });
  });

  it("offers only valid editor/preview pairing controls", () => {
    expect(workspaceControlsForLayout(edit)).toEqual({
      addEditor: false,
      addPreview: true,
      closePreview: false,
    });
    expect(workspaceControlsForLayout(preview)).toEqual({
      addEditor: true,
      addPreview: false,
      closePreview: false,
    });
    expect(workspaceControlsForLayout(split)).toEqual({
      addEditor: false,
      addPreview: false,
      closePreview: true,
    });
    expect(workspaceControlsForLayout(about)).toEqual({
      addEditor: false,
      addPreview: false,
      closePreview: false,
    });
  });
});

describe("view selection", () => {
  it("falls back to the stored view after a responsive fold", () => {
    const active = activeViewForLayouts(baseConfig.views, preview, split, true);
    expect(active?.key).toBe("preview");

    const viewerViews = baseConfig.views.filter((view) =>
      ["about", "split"].includes(view.key)
    );
    expect(activeViewForLayouts(viewerViews, preview, split, true)?.key).toBe(
      "split"
    );
  });

  it("selects no workspace view on another route", () => {
    expect(
      activeViewForLayouts(baseConfig.views, split, split, false)
    ).toBeNull();
  });
});

describe("workspace navigation", () => {
  it("strips an absolute app origin", () => {
    expect(
      workspaceTargetForLayout(
        false,
        "https://gooey.ai/agent/?run_id=run-1&uid=user-1"
      )
    ).toBe("/agent/?run_id=run-1&uid=user-1");
  });

  it("does not navigate when the workspace is active", () => {
    expect(workspaceTargetForLayout(true, "/agent/")).toBeNull();
  });

  it("hides panes until storage hydration completes", () => {
    expect(paneVisibility(false)).toBe("hidden");
    expect(paneVisibility(true)).toBe("visible");
  });
});

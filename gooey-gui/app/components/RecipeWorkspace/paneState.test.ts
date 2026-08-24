import { describe, expect, it } from "vitest";

import {
  collapsePane,
  initialPaneLayout,
  layoutAfterSelectingView,
  layoutForView,
  normalizePaneLayout,
  paneRolesForLayout,
  paneVisibility,
  shownLayout,
  selectedWorkspaceView,
  storedPaneLayout,
  viewAfterRun,
  viewForLayout,
  workspaceControlsForLayout,
  workspaceTargetForView,
} from "./paneState";

const about = layoutForView("about");
const edit = layoutForView("edit");
const preview = layoutForView("preview");
const split = layoutForView("split");

describe("layoutForView / viewForLayout", () => {
  it("expands a view name into three booleans", () => {
    expect(layoutForView("edit")).toEqual({
      mode: "work",
      editorOpen: true,
      previewOpen: false,
    });
    expect(layoutForView("preview")).toEqual({
      mode: "work",
      editorOpen: false,
      previewOpen: true,
    });
    expect(layoutForView("split")).toEqual({
      mode: "work",
      editorOpen: true,
      previewOpen: true,
    });
  });

  it("round-trips back to the view name", () => {
    expect(viewForLayout(edit)).toBe("edit");
    expect(viewForLayout(preview)).toBe("preview");
    expect(viewForLayout(split)).toBe("split");
  });
});

describe("collapsePane", () => {
  it("closes the named pane when something is left to show", () => {
    expect(collapsePane(split, "editor")).toEqual(preview);
    expect(collapsePane(split, "preview")).toEqual(edit);
  });

  it("refuses to close the last open pane", () => {
    expect(collapsePane(edit, "editor")).toEqual(edit);
    expect(collapsePane(preview, "preview")).toEqual(preview);
  });

  it("closes the preview beside About", () => {
    expect(collapsePane(about, "preview")).toEqual({
      mode: "about",
      editorOpen: true,
      previewOpen: false,
    });
  });
});

describe("layoutAfterSelectingView", () => {
  it("replaces the layout outright", () => {
    expect(layoutAfterSelectingView(edit, "about")).toEqual(about);
  });
});

describe("workspaceControlsForLayout", () => {
  it("offers the pairing control the current layout is missing", () => {
    expect(workspaceControlsForLayout(edit)).toEqual({
      addEdit: false,
      addPreview: true,
      mergePreview: false,
    });
    expect(workspaceControlsForLayout(preview)).toEqual({
      addEdit: true,
      addPreview: false,
      mergePreview: false,
    });
    expect(workspaceControlsForLayout(split)).toEqual({
      addEdit: false,
      addPreview: false,
      mergePreview: true,
    });
  });

  it("offers nothing on About", () => {
    expect(workspaceControlsForLayout(about)).toEqual({
      addEdit: false,
      addPreview: false,
      mergePreview: false,
    });
  });
});

describe("normalizePaneLayout", () => {
  it("falls back to the initial view when every pane is shut", () => {
    expect(
      normalizePaneLayout(
        { mode: "work", editorOpen: false, previewOpen: false },
        "split"
      )
    ).toEqual(split);
  });

  it("falls back on a missing or malformed value", () => {
    expect(normalizePaneLayout(null, "about")).toEqual(about);
  });
});

describe("workspaceTargetForView", () => {
  it("passes an app-relative href through", () => {
    expect(workspaceTargetForView(false, "/agent/")).toBe("/agent/");
  });

  it("strips the origin off an absolute one", () => {
    expect(
      workspaceTargetForView(
        false,
        "http://localhost:3000/agent/?run_id=run-1&uid=user-1"
      )
    ).toBe("/agent/?run_id=run-1&uid=user-1");
  });

  it("returns null when the workspace is already the current tab", () => {
    expect(workspaceTargetForView(true, "/agent/")).toBeNull();
  });
});

describe("selectedWorkspaceView", () => {
  it("names no view off the workspace", () => {
    expect(selectedWorkspaceView("split", false)).toBeNull();
    expect(selectedWorkspaceView("split", true)).toBe("split");
  });
});

describe("storedPaneLayout / initialPaneLayout", () => {
  it("reads the stored layout in preference to the initial view", () => {
    expect(
      storedPaneLayout(
        { getItem: () => JSON.stringify(edit) },
        "recipe-layout",
        "split"
      )
    ).toEqual(edit);
  });

  it("lets navigation state outrank both storage and the initial view", () => {
    expect(
      initialPaneLayout(
        { getItem: () => JSON.stringify(edit) },
        "recipe-layout",
        "about",
        { recipeView: "split" }
      )
    ).toEqual(split);
  });
});

describe("viewAfterRun", () => {
  it("lands a finished run on Split from the views with no output", () => {
    expect(viewAfterRun("edit", false)).toBe("split");
    expect(viewAfterRun("about", false)).toBe("split");
  });

  it("leaves a view that already shows output alone", () => {
    expect(viewAfterRun("split", false)).toBe("split");
    expect(viewAfterRun("preview", false)).toBe("preview");
  });

  it("does not move while the run is still going", () => {
    expect(viewAfterRun("edit", true)).toBe("edit");
  });
});

describe("paneRolesForLayout", () => {
  // About shares the row with the preview exactly as Split does, so it gets the same
  // major/minor pair. Reading the preview as solo here is what clipped it: the pane held 40%
  // of the row while its content was laid out at the full width of it.
  it("pairs the preview with whichever of About or Editor is showing", () => {
    expect(paneRolesForLayout(about)).toEqual({
      about: "major",
      editor: "closed",
      preview: "minor",
    });
    expect(paneRolesForLayout(split)).toEqual({
      about: "closed",
      editor: "major",
      preview: "minor",
    });
  });

  it("gives a pane with no company the whole row", () => {
    expect(paneRolesForLayout(edit)).toEqual({
      about: "closed",
      editor: "solo",
      preview: "closed",
    });
    expect(paneRolesForLayout(preview)).toEqual({
      about: "closed",
      editor: "closed",
      preview: "solo",
    });
  });

  // About keeps `editorOpen` set while the editor pane stays shut, so the role has to come
  // from what is on screen rather than from the flag.
  it("reads the role off what is shown, not off the flags", () => {
    expect(paneRolesForLayout(collapsePane(about, "preview"))).toEqual({
      about: "solo",
      editor: "closed",
      preview: "closed",
    });
  });
});

describe("shownLayout", () => {
  // A config pane that has claimed the row drops the preview from what is shown, without
  // touching the split stored behind it - leaving that pane brings the split straight back.
  it("drops the preview for a full-width editor without touching the stored split", () => {
    expect(shownLayout(split, true)).toEqual(edit);
    expect(shownLayout(split, false)).toEqual(split);
    expect(paneRolesForLayout(shownLayout(split, true))).toEqual({
      about: "closed",
      editor: "solo",
      preview: "closed",
    });
  });

  it("withdraws the pairing controls a claimed row would contradict", () => {
    expect(workspaceControlsForLayout(shownLayout(split, true), true)).toEqual({
      addEdit: false,
      addPreview: false,
      mergePreview: false,
    });
  });

  // The claim only reaches the editor. About and a solo preview have no config pane open,
  // so they are left exactly as they were.
  it("only reaches the editor", () => {
    expect(shownLayout(about, true)).toEqual(about);
    expect(shownLayout(preview, true)).toEqual(preview);
    expect(workspaceControlsForLayout(preview, true)).toEqual({
      addEdit: true,
      addPreview: false,
      mergePreview: false,
    });
  });
});

describe("paneVisibility", () => {
  it("hides the panes until the stored layout has loaded", () => {
    expect(paneVisibility(false)).toBe("hidden");
    expect(paneVisibility(true)).toBe("visible");
  });
});

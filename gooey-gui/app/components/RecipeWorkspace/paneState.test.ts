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

function main() {
  assertDeepEqual(layoutForView("edit"), {
    mode: "work",
    editorOpen: true,
    previewOpen: false,
  });
  assertDeepEqual(layoutForView("preview"), {
    mode: "work",
    editorOpen: false,
    previewOpen: true,
  });
  assertDeepEqual(layoutForView("split"), {
    mode: "work",
    editorOpen: true,
    previewOpen: true,
  });

  assertEqual(
    viewForLayout({ mode: "work", editorOpen: true, previewOpen: false }),
    "edit"
  );
  assertEqual(
    viewForLayout({ mode: "work", editorOpen: false, previewOpen: true }),
    "preview"
  );
  assertEqual(
    viewForLayout({ mode: "work", editorOpen: true, previewOpen: true }),
    "split"
  );

  const split = layoutForView("split");
  assertDeepEqual(collapsePane(split, "editor"), layoutForView("preview"));
  assertDeepEqual(collapsePane(split, "preview"), layoutForView("edit"));

  const edit = layoutForView("edit");
  const preview = layoutForView("preview");
  assertDeepEqual(collapsePane(edit, "editor"), edit);
  assertDeepEqual(collapsePane(preview, "preview"), preview);
  assertDeepEqual(
    layoutAfterSelectingView(edit, "about"),
    layoutForView("about")
  );

  const about = layoutForView("about");
  assertDeepEqual(workspaceControlsForLayout(edit), {
    addEdit: false,
    addPreview: true,
    mergePreview: false,
  });
  assertDeepEqual(workspaceControlsForLayout(preview), {
    addEdit: true,
    addPreview: false,
    mergePreview: false,
  });
  assertDeepEqual(workspaceControlsForLayout(split), {
    addEdit: false,
    addPreview: false,
    mergePreview: true,
  });
  assertDeepEqual(workspaceControlsForLayout(about), {
    addEdit: false,
    addPreview: false,
    mergePreview: false,
  });
  assertDeepEqual(collapsePane(about, "preview"), {
    mode: "about",
    editorOpen: true,
    previewOpen: false,
  });

  assertDeepEqual(
    normalizePaneLayout(
      { mode: "work", editorOpen: false, previewOpen: false },
      "split"
    ),
    layoutForView("split")
  );
  assertDeepEqual(normalizePaneLayout(null, "about"), {
    mode: "about",
    editorOpen: true,
    previewOpen: true,
  });

  assertEqual(workspaceTargetForView(false, "/agent/"), "/agent/");
  assertEqual(
    workspaceTargetForView(
      false,
      "http://localhost:3000/agent/?run_id=run-1&uid=user-1"
    ),
    "/agent/?run_id=run-1&uid=user-1"
  );
  assertEqual(workspaceTargetForView(true, "/agent/"), null);
  assertEqual(selectedWorkspaceView("split", false), null);
  assertEqual(selectedWorkspaceView("split", true), "split");

  assertDeepEqual(
    storedPaneLayout(
      {
        getItem: () =>
          JSON.stringify({
            mode: "work",
            editorOpen: true,
            previewOpen: false,
          }),
      },
      "recipe-layout",
      "split"
    ),
    layoutForView("edit")
  );
  assertDeepEqual(
    initialPaneLayout(
      {
        getItem: () => JSON.stringify(layoutForView("edit")),
      },
      "recipe-layout",
      "about",
      { recipeView: "split" }
    ),
    layoutForView("split")
  );

  assertEqual(viewAfterRun("edit", false), "split");
  assertEqual(viewAfterRun("split", false), "split");
  assertEqual(viewAfterRun("about", false), "split");
  assertEqual(viewAfterRun("preview", false), "preview");
  assertEqual(viewAfterRun("edit", true), "edit");

  // About shares the row with the preview exactly as Split does, so it gets the same
  // major/minor pair. Reading the preview as solo here is what clipped it: the pane held 40%
  // of the row while its content was laid out at the full width of it.
  assertDeepEqual(paneRolesForLayout(about), {
    about: "major",
    editor: "closed",
    preview: "minor",
  });
  assertDeepEqual(paneRolesForLayout(split), {
    about: "closed",
    editor: "major",
    preview: "minor",
  });
  assertDeepEqual(paneRolesForLayout(edit), {
    about: "closed",
    editor: "solo",
    preview: "closed",
  });
  assertDeepEqual(paneRolesForLayout(preview), {
    about: "closed",
    editor: "closed",
    preview: "solo",
  });
  // About keeps `editorOpen` set while the editor pane stays shut, so the role has to come
  // from what is on screen rather than from the flag.
  assertDeepEqual(paneRolesForLayout(collapsePane(about, "preview")), {
    about: "solo",
    editor: "closed",
    preview: "closed",
  });

  // A config pane that has claimed the row drops the preview from what is shown, without
  // touching the split stored behind it - leaving that pane brings the split straight back.
  assertDeepEqual(shownLayout(split, true), layoutForView("edit"));
  assertDeepEqual(shownLayout(split, false), split);
  assertDeepEqual(paneRolesForLayout(shownLayout(split, true)), {
    about: "closed",
    editor: "solo",
    preview: "closed",
  });
  assertDeepEqual(workspaceControlsForLayout(shownLayout(split, true), true), {
    addEdit: false,
    addPreview: false,
    mergePreview: false,
  });
  // The claim only reaches the editor. About and a solo preview have no config pane open,
  // so they are left exactly as they were.
  assertDeepEqual(shownLayout(about, true), about);
  assertDeepEqual(shownLayout(preview, true), preview);
  assertDeepEqual(workspaceControlsForLayout(preview, true), {
    addEdit: true,
    addPreview: false,
    mergePreview: false,
  });

  assertEqual(paneVisibility(false), "hidden");
  assertEqual(paneVisibility(true), "visible");
}

function assertEqual(actual: unknown, expected: unknown) {
  if (actual !== expected) {
    throw new Error(`Expected ${String(expected)}, received ${String(actual)}`);
  }
}

function assertDeepEqual(actual: unknown, expected: unknown) {
  const actualJson = JSON.stringify(actual);
  const expectedJson = JSON.stringify(expected);
  if (actualJson !== expectedJson) {
    throw new Error(`Expected ${expectedJson}, received ${actualJson}`);
  }
}

main();

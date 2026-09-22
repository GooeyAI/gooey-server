import { describe, expect, it, vi } from "vitest";

import type { PageShellConfig } from "@gooey-types/recipe_workspace_props";
import {
  activeViewForLayouts,
  appRelativeHref,
  collapsePane,
  foldForNarrowViewport,
  isRootLayout,
  isViewOnlyNavigation,
  layoutForEditorPane,
  layoutFromViewParam,
  layoutsEqual,
  paneRolesForLayout,
  revealRunOutput,
  shouldRevealRunOutput,
  singleLayout,
  splitLayout,
  VIEW_PARAM,
  viewParamForLayout,
  withViewParam,
  workspaceControlsForLayout,
  workspaceHrefToNavigate,
  workspaceLayoutFromUrl,
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
});

describe("shouldRevealRunOutput", () => {
  it("is true only for the editor on its own", () => {
    // The one view a run would start out of sight from.
    expect(shouldRevealRunOutput(edit)).toBe(true);
    expect(shouldRevealRunOutput(preview)).toBe(false);
    expect(shouldRevealRunOutput(about)).toBe(false);
    expect(shouldRevealRunOutput(split)).toBe(false);
    expect(shouldRevealRunOutput(singleLayout("about"))).toBe(false);
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

  it("keeps a config pane reachable when the split folds away from it", () => {
    // An About card naming a pane, tapped on a phone by someone whose narrow surface is the
    // chat: the split would fold to the chat, so the editor alone stands in for it.
    expect(layoutForEditorPane(split, "knowledge", "preview", true)).toEqual(
      edit
    );
    expect(layoutForEditorPane(split, "knowledge", "editor", true)).toEqual(
      split
    );
    expect(layoutForEditorPane(split, "knowledge", "preview", false)).toEqual(
      split
    );
  });

  it("leaves a target that names no pane alone", () => {
    expect(layoutForEditorPane(preview, null, "preview", true)).toEqual(
      preview
    );
    expect(layoutForEditorPane(about, undefined, "preview", true)).toEqual(
      about
    );
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
      workspaceHrefToNavigate(
        false,
        "https://gooey.ai/agent/?run_id=run-1&uid=user-1"
      )
    ).toBe("/agent/?run_id=run-1&uid=user-1");
  });

  it("does not navigate when the workspace is active", () => {
    expect(workspaceHrefToNavigate(true, "/agent/")).toBeNull();
  });

  it("relativizes any server-sent href, keeping the query", () => {
    // Handed an absolute url, `navigate` resolves it against the origin and 404s on
    // `/http://localhost:3000/agent/...` - so every navigation off a server-sent href has
    // to come through here, the rail's Ask Gooey included.
    expect(
      appRelativeHref("http://localhost:3000/agent/?run_id=32i1&uid=1rEt")
    ).toBe("/agent/?run_id=32i1&uid=1rEt");
    expect(appRelativeHref("https://gooey.ai/agent/#tools")).toBe(
      "/agent/#tools"
    );
    // already a path: left exactly as it is
    expect(appRelativeHref("/agent/?run_id=32i1")).toBe("/agent/?run_id=32i1");
  });
});

const url = (path: string) => new URL(path, "https://gooey.ai");

describe("the view lives in the url", () => {
  it("selects only a view the server actually declared", () => {
    expect(layoutFromViewParam(baseConfig, "edit")).toEqual(edit);
    expect(layoutFromViewParam(baseConfig, "not-a-view")).toBeNull();
    expect(layoutFromViewParam(baseConfig, null)).toBeNull();
  });

  it("falls back to what the url is for when it names no view", () => {
    expect(workspaceLayoutFromUrl(baseConfig, null)).toEqual(
      baseConfig.initial_layout
    );
    expect(workspaceLayoutFromUrl(baseConfig, "nonsense")).toEqual(
      baseConfig.initial_layout
    );
  });

  it("lets a route's own view outrank the page default, and the url outrank both", () => {
    const onPreview = { ...baseConfig, route_layout: preview };
    expect(workspaceLayoutFromUrl(onPreview, null)).toEqual(preview);
    expect(workspaceLayoutFromUrl(onPreview, "edit")).toEqual(edit);
  });

  it("round-trips a layout through its key", () => {
    const key = viewParamForLayout(baseConfig.views, edit);
    expect(key).toBe("edit");
    expect(layoutFromViewParam(baseConfig, key)).toEqual(edit);
  });

  it("has no key for a layout no view declares, so the url is left alone", () => {
    expect(
      viewParamForLayout(baseConfig.views, splitLayout("about", "editor"))
    ).toBeNull();
  });

  it("names the view on a link without disturbing the rest of the url", () => {
    expect(withViewParam("/agent/my-bot/?run_id=r1", "edit")).toBe(
      "/agent/my-bot/?run_id=r1&view=edit"
    );
    expect(withViewParam("/agent/my-bot/", null)).toBe("/agent/my-bot/");
    // replaces rather than appends a second one
    expect(withViewParam("/agent/?view=about", "edit")).toBe(
      "/agent/?view=edit"
    );
  });
});

describe("picking a view costs no server render", () => {
  it("is a view-only navigation when nothing else moved", () => {
    expect(
      isViewOnlyNavigation(url("/agent/a/"), url("/agent/a/?view=edit"))
    ).toBe(true);
    expect(
      isViewOnlyNavigation(
        url("/agent/a/?view=about"),
        url("/agent/a/?view=edit")
      )
    ).toBe(true);
    expect(
      isViewOnlyNavigation(
        url("/agent/a/?run_id=r1&view=about"),
        url("/agent/a/?run_id=r1&view=edit")
      )
    ).toBe(true);
  });

  it("is not, when anything else moved - or nothing did", () => {
    // a different page still has to be fetched
    expect(
      isViewOnlyNavigation(url("/agent/a/"), url("/agent/b/?view=edit"))
    ).toBe(false);
    // a different run is different data
    expect(
      isViewOnlyNavigation(
        url("/agent/a/?run_id=r1"),
        url("/agent/a/?run_id=r2&view=edit")
      )
    ).toBe(false);
    // identical urls are a form post, which the caller's own rules decide
    expect(
      isViewOnlyNavigation(
        url("/agent/a/?view=edit"),
        url("/agent/a/?view=edit")
      )
    ).toBe(false);
  });

  it("survives the form post that used to reset the view", () => {
    // gooey-gui posts to `"?" + searchParams`, so the view is still in the url afterwards -
    // which is the whole reason this replaced the hydration token.
    const afterPick = url("/agent/my-bot/?view=edit");
    const afterPost = url("/agent/my-bot/?view=edit");
    expect(
      workspaceLayoutFromUrl(baseConfig, afterPost.searchParams.get(VIEW_PARAM))
    ).toEqual(
      workspaceLayoutFromUrl(baseConfig, afterPick.searchParams.get(VIEW_PARAM))
    );
    expect(
      workspaceLayoutFromUrl(baseConfig, afterPost.searchParams.get(VIEW_PARAM))
    ).toEqual(edit);
  });
});

describe("revealRunOutput", () => {
  it("swaps a lone editor for the run layout, once the submit is away", () => {
    vi.useFakeTimers();
    const picked: unknown[] = [];
    revealRunOutput(edit, split, (next) => picked.push(next));
    expect(picked).toEqual([]);
    vi.runAllTimers();
    expect(picked).toEqual([split]);
    vi.useRealTimers();
  });

  it("leaves every other view alone - they were each chosen to show something", () => {
    vi.useFakeTimers();
    const picked: unknown[] = [];
    for (const layout of [about, preview, split]) {
      revealRunOutput(layout, split, (next) => picked.push(next));
    }
    vi.runAllTimers();
    expect(picked).toEqual([]);
    vi.useRealTimers();
  });
});

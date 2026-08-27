import { describe, expect, it } from "vitest";

import type { SurfaceId } from "@gooey-types/recipe_workspace_props";
import type { TreeNode } from "../../renderer";
import { namedSurfaceSlots } from "./surfaceSlots";

describe("namedSurfaceSlots", () => {
  it("uses the child slot node without adding a DOM wrapper", () => {
    const about = slotNode("about");
    const editor = slotNode("editor");
    const preview = slotNode("preview");

    const slots = namedSurfaceSlots([
      about.surface,
      editor.surface,
      preview.surface,
    ]);

    expect(slots.about).toBe(about.slot);
    expect(slots.editor).toBe(editor.slot);
    expect(slots.preview).toBe(preview.slot);
  });

  it("rejects missing and malformed slots", () => {
    const about = slotNode("about");
    const editor = slotNode("editor");

    expect(() => namedSurfaceSlots([about.surface, editor.surface])).toThrow(
      "missing preview surface"
    );
    expect(() =>
      namedSurfaceSlots([
        { ...about.surface, children: [] },
        editor.surface,
        slotNode("preview").surface,
      ])
    ).toThrow("exactly one slot node");
  });
});

function slotNode(surface: SurfaceId): {
  surface: TreeNode;
  slot: TreeNode;
} {
  const slot: TreeNode = {
    name: "div",
    props: {},
    children: [],
  };
  return {
    surface: {
      name: "RecipeSurface",
      props: { surface },
      children: [slot],
    },
    slot,
  };
}

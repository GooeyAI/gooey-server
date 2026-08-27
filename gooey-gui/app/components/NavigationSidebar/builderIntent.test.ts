import { describe, expect, it } from "vitest";

import { navigationStateWithoutBuilderIntent } from "./builderIntent";

describe("navigationStateWithoutBuilderIntent", () => {
  it("removes only the consumed intent", () => {
    expect(
      navigationStateWithoutBuilderIntent({
        builderIntent: "open",
        workspaceLayout: {
          kind: "split",
          primary: "editor",
          secondary: "preview",
        },
      })
    ).toEqual({
      workspaceLayout: {
        kind: "split",
        primary: "editor",
        secondary: "preview",
      },
    });
  });

  it("returns null once nothing is left", () => {
    expect(
      navigationStateWithoutBuilderIntent({ builderIntent: "open" })
    ).toBeNull();
    expect(navigationStateWithoutBuilderIntent(null)).toBeNull();
  });
});

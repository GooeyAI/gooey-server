import { describe, expect, it } from "vitest";

import {
  builderOpenNavigationState,
  builderTargetHref,
  navigationStateWithoutBuilderIntent,
  readBuilderIntent,
} from "./builderIntent";

describe("builderOpenNavigationState", () => {
  it("is read back as an open intent", () => {
    // The rail builds this for a tab that cannot hold the panel; the effect that acts on
    // arrival reads it with `readBuilderIntent`. If the two ever disagree, clicking Ask
    // Gooey from Deploy would navigate and then sit there doing nothing.
    expect(readBuilderIntent(builderOpenNavigationState())).toBe("open");
  });

  it("is dropped once consumed, so Back does not reopen the panel", () => {
    expect(
      navigationStateWithoutBuilderIntent(builderOpenNavigationState())
    ).toBeNull();
  });
});

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

describe("builderTargetHref", () => {
  it("relativizes the server's absolute url", () => {
    // Left absolute, `navigate` resolved it against the origin and the rail's Ask Gooey
    // landed on `/http://localhost:3000/agent/?run_id=...` - a 404 - from Deploy and API.
    expect(
      builderTargetHref("http://localhost:3000/agent/?run_id=32i1&uid=1rEt")
    ).toBe("/agent/?run_id=32i1&uid=1rEt");
  });

  it("is null where the page holds the panel already", () => {
    expect(builderTargetHref(null)).toBeNull();
    expect(builderTargetHref(undefined)).toBeNull();
    expect(builderTargetHref("")).toBeNull();
  });
});

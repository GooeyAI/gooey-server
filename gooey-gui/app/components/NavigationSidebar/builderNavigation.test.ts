import { describe, expect, it } from "vitest";

import {
  builderOpenEventName,
  navigationStateWithoutBuilderIntent,
} from "./builderNavigation";

describe("builderOpenEventName", () => {
  it("names the panel's open command", () => {
    expect(builderOpenEventName("builder-sidebar", "open")).toBe(
      "builder-sidebar:open"
    );
  });

  it("names nothing without an intent", () => {
    expect(builderOpenEventName("builder-sidebar", null)).toBeNull();
  });

  it("names nothing without an event key", () => {
    expect(builderOpenEventName("", "open")).toBeNull();
    expect(builderOpenEventName(undefined, "open")).toBeNull();
  });
});

describe("navigationStateWithoutBuilderIntent", () => {
  // The intent is consumed on arrival, but layout-v2's own navigation state travels in the
  // same slot and has to survive - clearing `usr` wholesale dropped it.
  it("removes only the consumed intent", () => {
    expect(
      navigationStateWithoutBuilderIntent({
        builderIntent: "open",
        recipeView: "split",
      })
    ).toEqual({ recipeView: "split" });
  });

  it("returns null once nothing is left", () => {
    expect(
      navigationStateWithoutBuilderIntent({ builderIntent: "open" })
    ).toBeNull();
    expect(navigationStateWithoutBuilderIntent(null)).toBeNull();
  });
});

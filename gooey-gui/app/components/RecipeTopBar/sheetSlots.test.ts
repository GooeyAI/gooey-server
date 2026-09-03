import { describe, expect, it } from "vitest";

import { sheetAudience, sheetSlots, type SheetSlot } from "./sheetSlots";

describe("sheetAudience", () => {
  it("puts a saved run's menu ahead of the permission-based two", () => {
    // Whether you could also edit the published run it came from does not change what a
    // saved run is.
    expect(sheetAudience({ onSavedRun: true, viewOnly: false })).toBe(
      "savedRun"
    );
    expect(sheetAudience({ onSavedRun: true, viewOnly: true })).toBe(
      "savedRun"
    );
  });

  it("splits a published run's own menu on whether it is yours to change", () => {
    expect(sheetAudience({ onSavedRun: false, viewOnly: false })).toBe(
      "editor"
    );
    expect(sheetAudience({ onSavedRun: false, viewOnly: true })).toBe(
      "visitor"
    );
  });
});

describe("sheetSlots", () => {
  it("gives an editor the full set, destinations first and Delete last", () => {
    expect(sheetSlots("editor")).toEqual([
      "integrations",
      "about",
      "preview",
      "edit",
      "newChat",
      "builder",
      "usage",
      "save",
      "deploy",
      "share",
      "api",
      "versions",
      "duplicate",
      "delete",
    ]);
  });

  it("gives a visitor no way to change the published run", () => {
    expect(sheetSlots("visitor")).toEqual([
      "integrations",
      "about",
      "preview",
      "edit",
      "newChat",
      "builder",
      "duplicate",
      "share",
      "api",
    ]);
  });

  it("leads a saved run with the way back, dropping the published run's actions", () => {
    expect(sheetSlots("savedRun")).toEqual([
      "parent",
      "preview",
      "edit",
      "newChat",
      "builder",
      "usage",
      "save",
      "duplicate",
      "api",
    ]);
  });

  it("offers the way back only from a saved run", () => {
    // `parent` is what carries it, and it is also the signal that the url points at a saved
    // run at all.
    expect(sheetSlots("editor")).not.toContain("parent");
    expect(sheetSlots("visitor")).not.toContain("parent");
  });

  it("keeps what belongs to a published run out of the other two menus", () => {
    // Deploying, sharing and the version record act on the published run, not on a saved
    // run of it - and none of them are a visitor's to touch either.
    const publishedRunOnly: SheetSlot[] = ["deploy", "versions", "delete"];
    for (const slot of publishedRunOnly) {
      expect(sheetSlots("savedRun")).not.toContain(slot);
      expect(sheetSlots("visitor")).not.toContain(slot);
    }
    expect(sheetSlots("savedRun")).not.toContain("integrations");
  });

  it("names every row at most once", () => {
    for (const audience of ["savedRun", "visitor", "editor"] as const) {
      const slots = sheetSlots(audience);
      expect(new Set(slots).size).toBe(slots.length);
    }
  });
});

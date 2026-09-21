import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import { pickDensity, TITLE_FLOOR } from "./barDensity";

describe("pickDensity", () => {
  it("keeps every label when the row has room for them", () => {
    expect(pickDensity(1200, [900, 780, 700, 670])).toBe(0);
  });

  it("sheds one step at a time rather than jumping to icons", () => {
    // 950 is short of the labelled row but clears the row without its inactive tab labels
    expect(pickDensity(950, [1000, 880, 800, 770])).toBe(1);
    expect(pickDensity(850, [1000, 880, 800, 770])).toBe(2);
  });

  it("settles on the tightest density when even that does not fit", () => {
    // Nothing more to give: the title has been truncating since the first step.
    expect(pickDensity(400, [1000, 880, 800, 770])).toBe(3);
  });

  it("reads a hole as 'never measured', which is how a fitted row is reported", () => {
    // The caller stops measuring once one fits, so the tighter entries are absent.
    expect(pickDensity(1000, [900, undefined, undefined, undefined])).toBe(0);
    expect(pickDensity(890, [900, 880, undefined, undefined])).toBe(1);
  });

  it("treats an exact fit as fitting", () => {
    expect(pickDensity(900, [900])).toBe(0);
  });

  it("leaves the title a floor to truncate within", () => {
    // Pinned because it is the one number here that is a judgement rather than a measurement.
    expect(TITLE_FLOOR).toBe(200);
  });
});

describe("what the density rules are allowed to touch", () => {
  /* The cost readout is a number, and a number has no icon to fall back to - so it is the
     one control in the bar that must survive every step. It survives structurally: it
     carries neither of the label classes. This pins that, because the way to break it is
     to add a rule here rather than to change anything about the cost itself. */
  // Relative to the package root, which is where vitest runs.
  const css = readFileSync(
    "app/components/RecipeTopBar/RecipeTopBar.css",
    "utf8"
  );
  const densityRules = css
    .split("}")
    .filter((block) => block.includes("[data-density="));

  it("has density rules at all, so the rest of this is checking something", () => {
    expect(densityRules.length).toBeGreaterThan(0);
  });

  it("never names the run cost or its separator", () => {
    for (const rule of densityRules) {
      const selector = rule.slice(rule.indexOf(".gooey-topbar"));
      expect(selector).not.toContain("gooey-topbar-cost");
      expect(selector).not.toContain("gooey-topbar-sep");
    }
  });

  it("never names the title, which truncates instead of shedding", () => {
    for (const rule of densityRules) {
      expect(rule).not.toContain("gooey-topbar-title");
    }
  });
});

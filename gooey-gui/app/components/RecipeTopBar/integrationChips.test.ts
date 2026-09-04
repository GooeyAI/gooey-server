import { describe, expect, it } from "vitest";

import { isIntegrationLabelled } from "./integrationChips";

describe("isIntegrationLabelled", () => {
  it("labels the first chip in a view-only bar", () => {
    expect(isIntegrationLabelled({ index: 0, count: 1, viewOnly: true })).toBe(
      true
    );
    expect(isIntegrationLabelled({ index: 0, count: 2, viewOnly: true })).toBe(
      true
    );
  });

  it("keeps an editor's chips minimal", () => {
    // The bar is already carrying the tab pills, the run controls and Update, so the chip
    // gives up its name rather than the row.
    expect(isIntegrationLabelled({ index: 0, count: 1, viewOnly: false })).toBe(
      false
    );
  });

  it("labels at most one chip, and none past two", () => {
    expect(isIntegrationLabelled({ index: 1, count: 2, viewOnly: true })).toBe(
      false
    );
    expect(isIntegrationLabelled({ index: 0, count: 3, viewOnly: true })).toBe(
      false
    );
  });
});

import { describe, expect, it } from "vitest";

import { LG_BREAKPOINT_PX, NARROW_QUERY, WIDE_QUERY } from "./breakpoints";

describe("the lg boundary", () => {
  it("matches the value Bootstrap's own lg utilities fold on", () => {
    // The CSS and every `d-lg-*` class in the markup use this number. If Bootstrap's lg
    // ever moves, this is the test that says so rather than a layout that quietly disagrees
    // with itself on one side of the breakpoint.
    expect(LG_BREAKPOINT_PX).toBe(992);
    expect(WIDE_QUERY).toBe("(min-width: 992px)");
  });

  it("makes narrow the exact complement of wide, with no gap between them", () => {
    // A viewport can only ever be one of the two. Written by hand these were 992 and
    // 991.98, which is correct but is two numbers that have to be edited together.
    expect(NARROW_QUERY).toBe("(max-width: 991.98px)");

    const wideFrom = Number(WIDE_QUERY.match(/([\d.]+)px/)![1]);
    const narrowTo = Number(NARROW_QUERY.match(/([\d.]+)px/)![1]);
    expect(narrowTo).toBeLessThan(wideFrom);
    // nothing lands in between: the gap is under one device pixel
    expect(wideFrom - narrowTo).toBeCloseTo(0.02, 5);
  });
});

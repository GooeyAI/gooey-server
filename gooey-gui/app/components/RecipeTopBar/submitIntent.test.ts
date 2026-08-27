import { describe, expect, it } from "vitest";

import { encodeSubmitIntent } from "./submitIntent";

describe("encodeSubmitIntent", () => {
  it("encodes one request-scoped discriminated action", () => {
    expect(encodeSubmitIntent({ kind: "run" })).toBe('{"kind":"run"}');
    expect(encodeSubmitIntent({ kind: "menu", item_key: "duplicate" })).toBe(
      '{"kind":"menu","item_key":"duplicate"}'
    );
  });
});

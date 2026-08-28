import { resolve } from "node:path";
import { defineConfig } from "vitest/config";

// Mirrors the `paths` in tsconfig.json. Without it a test can only cover modules whose
// aliased imports are all types - anything importing `~/...` for real fails to resolve, and
// the failure looks like a missing file rather than a missing alias.
export default defineConfig({
  resolve: {
    alias: {
      "~": resolve(__dirname, "app"),
      "@gooey-types": resolve(__dirname, "../gooey_gui/types"),
    },
  },
});

import { describe, expect, it } from "vitest";

import {
  panelOpenForStorage,
  shouldRestorePanel,
  type PanelEntry,
} from "./appShellContext";

const commandedOpen: PanelEntry = {
  open: true,
  storageKey: "workflow-a",
  hydrated: true,
  commanded: true,
};

describe("panel storage isolation", () => {
  it("uses the current workflow's settled panel state", () => {
    expect(panelOpenForStorage(commandedOpen, "workflow-a", false)).toBe(true);
    expect(shouldRestorePanel(commandedOpen, "workflow-a")).toBe(false);
  });

  it("restores defaults when the workflow storage key changes", () => {
    expect(panelOpenForStorage(commandedOpen, "workflow-b", false)).toBe(false);
    expect(shouldRestorePanel(commandedOpen, "workflow-b")).toBe(true);
  });
});

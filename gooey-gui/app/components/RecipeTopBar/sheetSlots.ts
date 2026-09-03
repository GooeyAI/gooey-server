/** Which rows the mobile sheet offers, and in what order.
 *
 * Kept as data rather than assembled inline: the order *is* the design, and three orderings
 * written out beside each other are readable in a way three nested conditions are not.
 * The component owns the rows themselves - what each one says and does - and this owns only
 * which of them appear and where.
 */

/** One row's identity. Not a label: what the row says depends on who is looking. */
export type SheetSlot =
  | "parent"
  | "integrations"
  | "about"
  | "preview"
  | "edit"
  | "newChat"
  | "builder"
  | "usage"
  | "save"
  | "deploy"
  | "share"
  | "api"
  | "versions"
  | "duplicate"
  | "delete";

/** The three states the page can be in, which is what decides the menu.
 *
 * `savedRun` first because it wins regardless of permission: a saved run is somewhere you
 * work, and whether you could also edit the published run it came from does not change that.
 */
export type SheetAudience = "savedRun" | "visitor" | "editor";

const SHEET_SLOTS: Record<SheetAudience, SheetSlot[]> = {
  // A saved run belongs to whoever opened it, while Deploy, Share, Versions, Delete and the
  // channels all act on the published run behind it - so they are not this menu's to offer.
  // It leads with the way back there instead.
  savedRun: [
    "parent",
    "preview",
    "edit",
    "newChat",
    "builder",
    "usage",
    "save",
    "duplicate",
    "api",
  ],
  // Someone else's published run. What presents it, plus the two ways to leave with a copy.
  // Nothing that would change it, and no list of its saved runs - that is its workspace's
  // to see.
  visitor: [
    "integrations",
    "about",
    "preview",
    "edit",
    "newChat",
    "builder",
    "duplicate",
    "share",
    "api",
  ],
  // The full set. Destinations first, then what you do to the published run, then what you
  // do to the record of it - Delete last, where a mis-tap is least likely to land.
  editor: [
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
  ],
};

export function sheetSlots(audience: SheetAudience): SheetSlot[] {
  return SHEET_SLOTS[audience];
}

/** Which menu the page is showing. A saved run's wins over the permission-based two. */
export function sheetAudience({
  onSavedRun,
  viewOnly,
}: {
  onSavedRun: boolean;
  viewOnly: boolean;
}): SheetAudience {
  if (onSavedRun) {
    return "savedRun";
  }
  return viewOnly ? "visitor" : "editor";
}

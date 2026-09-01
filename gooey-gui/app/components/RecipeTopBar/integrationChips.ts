/** Whether a demo chip ("Try in WhatsApp") shows its name beside its icon.
 *
 * Only in the view-only bar. There the chip is the page's call to action, and the bar has
 * the room. An editor's bar is already carrying the tab pills, the run controls and Update,
 * so chips there stay icons - they keep their name in the `title`, the `aria-label` and the
 * ... menu, so nothing is lost but the width.
 *
 * Past the first chip, or past two chips, there is no room for a label in either bar.
 */
export function isIntegrationLabelled({
  index,
  count,
  viewOnly,
}: {
  index: number;
  count: number;
  viewOnly: boolean;
}): boolean {
  return viewOnly && index === 0 && count <= 2;
}

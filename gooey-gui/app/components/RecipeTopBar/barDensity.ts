/** How much of the bar's text is showing.
 *
 * Each step sheds the next least useful label. Two things are never shed: the workflow's
 * title, which truncates instead and is the one thing an icon cannot stand in for, and the
 * run cost, which is a number with no icon form at all.
 *
 * Measured rather than pinned to a width, because what the bar needs is not a constant. A
 * visitor's two tabs and an editor's four differ by ~100px before a deployment chip or a
 * Usage tab joins either, and the labels vary by recipe - "Edit" is 26px, "How it works"
 * is 87px. A breakpoint has to assume the worst case, so it collapses a bar that had room;
 * this collapses the bar that has none.
 */
export type BarDensity = 0 | 1 | 2 | 3;

export const BAR_DENSITIES: readonly BarDensity[] = [0, 1, 2, 3];

/** What the title keeps for itself before anything else gives way. Enough to tell two
 *  workflows apart; past this it ellipsises, which it may do at any density. */
export const TITLE_FLOOR = 200;

/** The roomiest density that fits, or the tightest one if none do.
 *
 * `needed[d]` is what the row measures at density `d`. A hole means it was never measured,
 * which is what happens once a roomier one has already fitted.
 */
export function pickDensity(
  available: number,
  needed: readonly (number | undefined)[]
): BarDensity {
  for (const density of BAR_DENSITIES) {
    const need = needed[density];
    if (need !== undefined && need <= available) return density;
  }
  return 3;
}

/** The width of a flex row's own content, gaps included.
 *
 * Not `scrollWidth`: these clusters are stretched to their grid track, so `scrollWidth`
 * reports the track whenever the content is narrower than it - which is exactly the case
 * this has to tell apart from the one where it is not.
 */
function contentWidth(el: Element | null): number {
  if (!el) return 0;
  const gap = parseFloat(getComputedStyle(el).columnGap) || 0;
  const kids = Array.from(el.children).filter((kid) => {
    const style = getComputedStyle(kid);
    // A shed label is still a child, but it is out of flow and costs the row nothing.
    return style.display !== "none" && style.position !== "absolute";
  });
  const total = kids.reduce(
    (sum, kid) => sum + kid.getBoundingClientRect().width,
    0
  );
  return total + Math.max(0, kids.length - 1) * gap;
}

/** What the row needs at whatever density it is currently rendered in.
 *
 * The title block is swapped for its floor: it is the one part that answers a shortage by
 * truncating, so its rendered width says what it was given rather than what it wants.
 */
export function neededWidth(bar: HTMLElement): number {
  const gap = parseFloat(getComputedStyle(bar).columnGap) || 0;
  const tabs = bar.querySelector<HTMLElement>(".gooey-topbar-tabs");
  const title = bar.querySelector<HTMLElement>(".gooey-topbar-titleblock");

  let left = contentWidth(bar.querySelector(".gooey-topbar-left"));
  if (title) {
    left = left - title.getBoundingClientRect().width + TITLE_FLOOR;
  }

  const tabsWidth = tabs?.getBoundingClientRect().width ?? 0;
  const right = contentWidth(bar.querySelector(".gooey-topbar-right"));

  return left + (tabsWidth ? tabsWidth + gap : 0) + right + gap;
}

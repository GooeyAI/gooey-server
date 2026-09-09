/** The one place the lg boundary is written down.
 *
 * Bootstrap's `lg` is what the CSS and the `d-lg-*` utilities fold on, so the JS that has to
 * agree with them derives from the same number rather than restating it. Two constants
 * written as complements of each other - 992 and 991.98 - is one edit away from disagreeing.
 */
export const LG_BREAKPOINT_PX = 992;

/** Matches when the viewport is lg or wider, i.e. where the two-pane layouts apply. */
export const WIDE_QUERY = `(min-width: ${LG_BREAKPOINT_PX}px)`;

/** The exact complement of `WIDE_QUERY`: below lg, where the rail becomes a drawer and the
 *  splits fold to a single pane. `.02` matches Bootstrap's own max-width convention. */
export const NARROW_QUERY = `(max-width: ${LG_BREAKPOINT_PX - 0.02}px)`;

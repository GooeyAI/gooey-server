/** The nav drawer's open command, shared by the two components that care about it.
 *
 * Below lg the rail is an off-canvas drawer, and the control that opens it lives in
 * RecipeTopBar - the sidebar's own mobile bar is gone, so the bar is the app's only header.
 * That puts the button and the state in different component trees with no common ancestor to
 * lift into, which is what this event bridges.
 *
 * A constant rather than a prop threaded through the server: nothing server-side changes when
 * the drawer opens, so routing it through session state would be a round-trip to tell one
 * client component what another already knows. The Builder panel's `:open` / `:close` commands
 * work the same way.
 */
export const NAV_DRAWER_OPEN_EVENT = "gooey:nav-drawer:open";

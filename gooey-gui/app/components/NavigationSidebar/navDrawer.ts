/** The nav drawer's open command. The control that opens it lives in RecipeTopBar, a
 * sibling with no common ancestor to lift the state into, and nothing server-side changes
 * when the drawer opens - so an event rather than a prop. */
export const NAV_DRAWER_OPEN_EVENT = "gooey:nav-drawer:open";

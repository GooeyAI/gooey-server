export const gooeyGuiRouteHeader = "X-GOOEY-GUI-ROUTE";

// Marker added to a submission's JSON body for submits the user did not ask for and should
// not be shown: a realtime-driven background refresh, and persisting a piece of chrome state
// such as whether the navigation rail is collapsed. Both post the whole form, and neither is
// a page load - so the global progress bar reads this and stays quiet.
//
// The server only reads `state`, so this extra key is ignored server-side.
export const silentSubmitKey = "__gooeySilentSubmit";

export const gooeyGuiRouteHeader = "X-GOOEY-GUI-ROUTE";

// Marker added to a submission's JSON body for realtime-driven background refreshes.
// The server only reads `state`, so this extra key is ignored server-side; the client
// uses it to keep the global progress bar silent for these submits.
export const realtimeRefreshKey = "__gooeyRealtimeRefresh";

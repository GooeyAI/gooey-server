/** Remix stores `location.state` under `history.state.usr`.
 *
 * The shell puts one-shot commands there - open this panel, show this layout - which have to
 * be dropped once acted on, or Back and refresh replay them. Both live in the same object,
 * so each is removed by key and the rest is left alone regardless of effect ordering.
 */
export function navigationStateWithout(
  state: unknown,
  key: string
): Record<string, unknown> | null {
  if (!state || typeof state !== "object") {
    return null;
  }
  const remaining = { ...(state as Record<string, unknown>) };
  delete remaining[key];
  return Object.keys(remaining).length ? remaining : null;
}

/** Drop one consumed command from the live history entry, in place. */
export function clearNavigationStateKey(key: string) {
  const historyState = window.history.state;
  if (!historyState?.usr) {
    return;
  }
  window.history.replaceState(
    { ...historyState, usr: navigationStateWithout(historyState.usr, key) },
    ""
  );
}

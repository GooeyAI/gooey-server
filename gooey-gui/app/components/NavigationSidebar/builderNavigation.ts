export function builderOpenEventName(
  eventKey: string | undefined,
  intent: "open" | null
): string | null {
  if (!eventKey || !intent) {
    return null;
  }
  return `${eventKey}:open`;
}

export function navigationStateWithoutBuilderIntent(
  state: unknown
): Record<string, unknown> | null {
  if (!state || typeof state !== "object") {
    return null;
  }
  const nextState = { ...(state as Record<string, unknown>) };
  delete nextState.builderIntent;
  if (!Object.keys(nextState).length) {
    return null;
  }
  return nextState;
}

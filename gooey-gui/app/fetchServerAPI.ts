export async function fetchServerAPI<T = unknown>(
  path: string,
  kwargs: Record<string, unknown> = {},
): Promise<T> {
  if (!path.startsWith("/__/")) {
    throw new Error(`fetchServerApi can only be used for internal API calls`);
  }
  let response = await fetch(path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(kwargs),
  });
  if (!response.ok) {
    let text = await response.text();
    throw new Error(`fetchServerApi ${path} failed: ${response.status} ${text}`);
  }
  return response.json() as Promise<T>;
}

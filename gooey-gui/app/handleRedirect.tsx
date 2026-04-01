import process from "process";
import settings from "./settings";

const redirectStatuses = [301, 302, 303, 307, 308];

export function handleRedirectResponse({
  response,
}: {
  response: Response;
}): string | null {
  // if the response is not a redirect, return null
  if (!redirectStatuses.includes(response.status)) return null;
  // get the redirect target
  const backendUrl = new URL(settings.SERVER_HOST!);
  const redirectUrl = new URL(response.headers.get("location") ?? "/");
  let newLocation;
  if (redirectUrl.host == backendUrl.host) {
    // strip the proxy host/port from the redirect target, so the user stays on the same host
    newLocation = redirectUrl.pathname + redirectUrl.search + redirectUrl.hash;
  } else {
    // if the redirect target is a different host, redirect to the full URL
    newLocation = redirectUrl.toString();
  }
  response.headers.set("location", newLocation);
  return newLocation;
}

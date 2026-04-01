import process from "process";
import type { LoaderArgs } from "@remix-run/node";
import path from "path";
import { Params } from "@remix-run/react";
import { handleRedirectResponse } from "~/handleRedirect";
import settings from "./settings";

export async function loader({ request, params }: LoaderArgs) {
  return await _proxy({ request, params });
}

export async function action({ request, params }: LoaderArgs) {
  return await _proxy({ request, params });
}

async function _proxy({
  request,
  params,
}: {
  params: Params;
  request: Request;
}) {
  const requestUrl = new URL(request.url);
  const backendUrl = new URL(settings.SERVER_HOST!);
  backendUrl.pathname = path.join(backendUrl.pathname, requestUrl.pathname);
  backendUrl.search = requestUrl.search;
  request.headers.delete("Host");
  const response = await fetch(backendUrl, {
    method: request.method,
    redirect: "manual",
    body: request.body ? await request.arrayBuffer() : null,
    headers: request.headers,
  });
  handleRedirectResponse({ response });
  return response;
}

import { cssBundleHref } from "@remix-run/css-bundle";
import type { LinksFunction } from "@remix-run/node";
import { json } from "@remix-run/node"; // Depends on the runtime you choose
import {
  isRouteErrorResponse,
  Links,
  LiveReload,
  Meta,
  Outlet,
  Scripts,
  ScrollRestoration,
  ShouldRevalidateFunction,
  useLoaderData,
  useRouteError,
} from "@remix-run/react";
import { captureRemixErrorBoundaryError } from "@sentry/remix";
import { globalProgressStyles, useGlobalProgress } from "~/global-progres-bar";
import {
  HydrationUtilsPostRender,
  HydrationUtilsPreRender,
} from "~/useHydrated";
import settings from "./settings";
import { ReactNode } from "react";

export const links: LinksFunction = () => [
  ...(cssBundleHref ? [{ rel: "stylesheet", href: cssBundleHref }] : []),
  ...globalProgressStyles(),
];

// export env vars to the client
export async function loader() {
  return json({
    ENV: {
      SENTRY_DSN: settings.SENTRY_DSN,
      SENTRY_SAMPLE_RATE: settings.SENTRY_SAMPLE_RATE,
      SENTRY_RELEASE: settings.SENTRY_RELEASE,
    },
  });
}
export const shouldRevalidate: ShouldRevalidateFunction = () => false;

export default function App() {
  const data = useLoaderData<typeof loader>();
  return (
    <Scaffold>
      <div
        id="portal"
        style={{ position: "fixed", left: 0, top: 0, zIndex: 9999 }}
      />
      <script
        // load client side env vars
        dangerouslySetInnerHTML={{
          __html: `window.ENV = ${JSON.stringify(data.ENV)};`,
        }}
      />
      <HydrationUtilsPreRender />
      <Outlet />
      <HydrationUtilsPostRender />
      <ScrollRestoration />
    </Scaffold>
  );
}

function Scaffold({ children }: { children?: ReactNode }) {
  useGlobalProgress();

  return (
    <html lang="en">
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width,initial-scale=1" />
        <Meta />
        <Links />
        <script
          src="https://kit.fontawesome.com/8af9787bd5.js"
          crossOrigin="anonymous"
        ></script>
      </head>
      <body>
        {children}
        <Scripts />
        <LiveReload />
      </body>
    </html>
  );
}

const reloadOnErrors = [
  "TypeError: Failed to fetch",
  "TypeError: Load failed",
  "Network Error",
  "NetworkError",
];

export function ErrorBoundary() {
  const error = useRouteError();

  if (
    reloadOnErrors.some((msg) =>
      `${error}`.toLowerCase().includes(msg.toLowerCase())
    )
  ) {
    window.location.reload();
  }

  captureRemixErrorBoundaryError(error);
  console.error(error);

  // when true, this is what used to go to `CatchBoundary`
  if (isRouteErrorResponse(error)) {
    return (
      <Scaffold>
        <p>Status: {error.status}</p>
        <pre>{JSON.stringify(error.data)}</pre>
      </Scaffold>
    );
  }

  return (
    <Scaffold>
      <h1>Uh oh ...</h1>
      <p>Something went wrong.</p>
      <pre>{`${error}`}</pre>
    </Scaffold>
  );
}

import type { LinksFunction } from "@remix-run/node";
import { json } from "@remix-run/node"; // Depends on the runtime you choose
import type { ShouldRevalidateFunction } from "@remix-run/react";
import {
  isRouteErrorResponse,
  Links,
  LiveReload,
  Meta,
  Outlet,
  Scripts,
  ScrollRestoration,
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
import type { ReactNode } from "react";

// Inter and Domine are the design system's two faces: Inter for UI text, Domine for display
// headings. Loaded here rather than as `@font-face` beside basiercircle's `.otf` files
// because Google serves the right subsets and formats per browser, and neither face ships
// with the repo. Only the v2 surfaces and the navigation rail use them - see
// `--gooey-font-ui` in app.css - so the rest of the app is unaffected by the extra request.
const FONT_LINKS: ReturnType<LinksFunction> = [
  { rel: "preconnect", href: "https://fonts.googleapis.com" },
  { rel: "preconnect", href: "https://fonts.gstatic.com", crossOrigin: "anonymous" },
  {
    rel: "stylesheet",
    href:
      "https://fonts.googleapis.com/css2?family=Domine:wght@400..700" +
      "&family=Inter:ital,opsz,wght@0,14..32,100..900;1,14..32,100..900" +
      "&display=swap",
  },
];

export const links: LinksFunction = () => [
  ...globalProgressStyles(),
  ...FONT_LINKS,
];

declare global {
  interface Window {
    ENV: typeof settings;
  }
}

// export env vars to the client
export async function loader() {
  return json({
    ENV: {
      SENTRY_DSN: settings.SENTRY_DSN,
      SENTRY_RELEASE: settings.SENTRY_RELEASE,
      SERVER_HOST: settings.SERVER_HOST,
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

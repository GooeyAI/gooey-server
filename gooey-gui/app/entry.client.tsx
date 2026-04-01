import { RemixBrowser, useLocation, useMatches } from "@remix-run/react";
import * as Sentry from "@sentry/remix";
import { useEffect } from "react";
import { hydrate } from "react-dom";

Sentry.init({
  dsn: window.ENV.SENTRY_DSN,
  release: window.ENV.SENTRY_RELEASE,
  environment: "client",
  integrations: [
    Sentry.browserTracingIntegration({
      useEffect,
      useLocation,
      useMatches,
    }),
    Sentry.replayIntegration(),
    Sentry.httpClientIntegration(),
  ],
  // Performance Monitoring
  tracesSampleRate: 0.005, // Capture X% of the transactions, reduce in production!
  // Session Replay
  replaysSessionSampleRate: 0, // This sets the sample rate at 10%. You may want to change it to 100% while in development and then sample at a lower rate in production.
  replaysOnErrorSampleRate: 1.0, // If you're not already sampling the entire session, change the sample rate to 100% when sampling sessions where errors occur.
  // This option is required for capturing headers and cookies.
  sendDefaultPii: true,
  // To enable offline events caching, use makeBrowserOfflineTransport to wrap existing transports and queue events using the browsers' IndexedDB storage.
  // Once your application comes back online, all events will be sent together.
  transport: Sentry.makeBrowserOfflineTransport(Sentry.makeFetchTransport),
  // You can use the ignoreErrors option to filter out errors that match a certain pattern.
  ignoreErrors: [
    /TypeError: Failed to fetch/i,
    /TypeError: Load failed/i,
    /(network)(\s*)(error)/i,
    /AbortError/i,
    /Detected popup close/i,
  ],
});

hydrate(<RemixBrowser />, document);

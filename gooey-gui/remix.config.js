require("dotenv/config");

const wixUrls =
  process.env.WIX_URLS?.trim()
    .split(/\s+/)
    .filter((it) => it) || [];

/** @type {import('@remix-run/dev').AppConfig} */
module.exports = {
  ignoredRouteFiles: ["**/.*", "**/*.module.css"],
  // appDirectory: "app",
  // assetsBuildDirectory: "public/build",
  // serverBuildPath: "build/index.js",
  // publicPath: "/build/",
  serverModuleFormat: "cjs",
  future: {
    v2_errorBoundary: true,
    v2_meta: true,
    v2_normalizeFormMethod: true,
    v2_routeConvention: true,
  },
  serverDependenciesToBundle: [
    /uppy/,
    /marked/,
    /nanoid/,
    /exifr/,
    /firebase-admin/,
    /glideapps/,
    /p-retry/,
    /p-queue/,
    /p-timeout/,
    /is-network-error/,
  ],
  routes(defineRoutes) {
    return defineRoutes((route) => {
      // A common use for this is catchall _routes.
      // - The first argument is the React Router path to match against
      // - The second is the relative filename of the route handler
      for (const path of wixUrls) {
        route(path, "wix.tsx", { id: "wix-" + path });
      }
      route("/__/health", "health.ts");
      route("/__/*", "proxy.tsx");
      route("/__/realtime/*", "realtime.tsx");
      route("*", "app.tsx", { id: "app" });
      route("/", "app.tsx", { id: "home" });
    });
  },
};

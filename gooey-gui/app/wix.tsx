import type { LoaderArgs } from "@remix-run/node";
import path from "path";
import type { Browser } from "puppeteer";

import MobileDetect from "mobile-detect";

const puppeteer = require("puppeteer");

declare global {
  var browser: Browser;
  var htmlCaches: Record<string, string>;
  var promiseCaches: Record<string, Promise<string>>;
}

if (typeof global.htmlCaches === "undefined") {
  global.htmlCaches = {};
  global.promiseCaches = {};
}

export async function loader({ request }: LoaderArgs) {
  const requestUrl = new URL(request.url);

  const isMobile = Boolean(
    new MobileDetect(request.headers.get("User-Agent") ?? "").mobile()
  );

  const wixUrl = new URL(
    process.env.WIX_SITE_URL || "https://www.help.gooey.ai"
  );
  wixUrl.pathname = path.join(wixUrl.pathname, requestUrl.pathname, "/");
  wixUrl.search = requestUrl.search;
  wixUrl.hash = `isMobile=${isMobile}`;
  const url = wixUrl.toString();

  let html = global.htmlCaches[url];
  let promise = loadPage(url, isMobile);
  if (!html) {
    html = await promise;
  }

  return new Response(html, {
    headers: {
      "content-type": "text/html; charset=utf-8",
    },
  });
}

async function loadPage(url: string, isMobile: boolean): Promise<string> {
  let promise = global.promiseCaches[url];
  if (!promise) {
    promise = _loadPage(url, isMobile);
    global.promiseCaches[url] = promise;
  }
  try {
    const html = await promise;
    global.htmlCaches[url] = html;
    return html;
  } finally {
    delete global.promiseCaches[url];
  }
}

async function _loadPage(url: string, isMobile: boolean): Promise<string> {
  if (!global.browser) {
    global.browser = await puppeteer.launch({
      headless: "new",
      args: ["--no-sandbox"],
    });
  }
  const page = await global.browser.newPage();
  try {
    page.setDefaultTimeout(60_000); // 1 minute
    let ua;
    if (isMobile) {
      ua =
        "Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.0.3 Mobile/15E148 Safari/604.1";
    } else {
      ua =
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/104.0.5112.79 Safari/537.36";
    }
    await page.setUserAgent(ua);
    await page.goto(url, { waitUntil: "networkidle0" });
    return await page.content();
  } finally {
    await page.close();
  }
}

//
// Cloudflare Worker that executes user-supplied JavaScript in an isolated,
// dynamically loaded worker via the Worker Loader binding
// (https://developers.cloudflare.com/workers/runtime-apis/bindings/worker-loader/).
//
// Cloudflare Workers disallow eval(), so the user code is wrapped in ES module
// code — inserted in expression position — which lets us evaluate expressions
// (e.g. an anonymous function) just like the old eval()-based executor.
//
// To deploy, run (from the repo root):
//    npx wrangler deploy -c functions/wrangler.toml
//    npx wrangler secret put GOOEY_AUTH_TOKEN -c functions/wrangler.toml
//

export default {
  async fetch(request, env, ctx) {
    if (!isAuthenticated(request, env)) {
      return new Response("Unauthorized", { status: 401 });
    }

    let { tag, code, variables, env: userEnv, gooey_memory } =
      await request.json();

    let moduleCode = buildModule(code || "");
    let worker = env.LOADER.get(await sha256(moduleCode), () => ({
      compatibilityDate: "2025-06-01",
      mainModule: "main.js",
      modules: { "main.js": moduleCode },
    }));

    let status, response;
    try {
      let res = await worker.getEntrypoint().fetch("https://executor/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ variables, env: userEnv, gooey_memory }),
      });
      response = await res.json();
      status = response.error ? 207 : 200;
    } catch (e) {
      status = 207;
      response = { error: toString(e), errorType: typeof e, gooey_memory };
    }

    for (let log of response.logs || []) {
      console[log.level === "error" ? "error" : "log"](
        `[${tag}]`,
        log.message,
      );
    }

    let body = JSON.stringify(response);
    return new Response(body, {
      status,
      headers: { "Content-Type": "application/json" },
    });
  },
};

const USER_CODE_PLACEHOLDER = "/*__GOOEY_USER_CODE__*/";

// The user code is inserted in expression position inside a module-scoped
// fetch handler, with `variables`, `process`, `GOOEY_MEMORY` and a
// log-capturing `console` shadowing the globals.
const MODULE_TEMPLATE = `
export default {
  async fetch(request) {
    let { variables, env, gooey_memory } = await request.json();
    let process = { env: env || {} };
    let GOOEY_MEMORY = gooey_memory;
    let logs = [];
    let console = captureConsole(logs);
    let retval = null, error = null;
    try {
      retval = (
${USER_CODE_PLACEHOLDER}
      );
      if (retval instanceof Function) {
        retval = retval(variables);
      }
      if (retval instanceof Promise) {
        retval = await retval;
      }
    } catch (e) {
      error = toString(e);
    }
    return Response.json({ retval, gooey_memory: GOOEY_MEMORY, logs, error });
  },
};

function captureConsole(logs) {
  return {
    log(...args) {
      logs.push({ level: "log", message: args.map(toString).join(" ") });
    },
    error(...args) {
      logs.push({ level: "error", message: args.map(toString).join(" ") });
    },
  };
}

${toString.toString()}
`;

function buildModule(code) {
  // .replace() with a function arg so "$" sequences in user code stay verbatim
  return MODULE_TEMPLATE.replace(USER_CODE_PLACEHOLDER, () => code);
}

function isAuthenticated(request, env) {
  let authorization = request.headers.get("Authorization");
  if (!authorization) return false;
  let parts = authorization.trim().split(" ");
  let token = parts[parts.length - 1];
  return token === env.GOOEY_AUTH_TOKEN;
}

async function sha256(text) {
  let digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(text),
  );
  return [...new Uint8Array(digest)]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function toString(obj) {
  if (typeof obj === "string") {
    return obj;
  } else if (obj instanceof Error) {
    return obj.stack || String(obj);
  }
  try {
    return JSON.stringify(obj);
  } catch (e) {
    return String(obj);
  }
}

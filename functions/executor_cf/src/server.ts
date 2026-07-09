//
// Executes user-provided ECMAScript modules in a sandboxed Cloudflare Dynamic Worker.
// https://developers.cloudflare.com/dynamic-workers/getting-started/
//
// To deploy, see wrangler.jsonc in this directory.
//

import { parse, type Options } from "acorn";
import { createWorker } from "@cloudflare/worker-bundler";
// Imported as a Text module (see rules in wrangler.jsonc): ENTRY_SOURCE is
// the file's source code as a string, not an executed module.
import EXECUTOR_SOURCE from "./executor.js";

interface ExecuteRequest {
  code: string;
  variables?: Record<string, unknown>;
  env?: Record<string, string>;
  gooey_memory?: unknown;
  package_json?: Record<string, unknown> | null;
}

export default {
  async fetch(request, env, ctx) {
    let {
      code,
      variables,
      env: userEnv,
      gooey_memory,
      package_json,
    } = await request.json<ExecuteRequest>();
    if (!package_json || !Object.keys(package_json).length) {
      package_json = null;
    }
    try {
      code = normalizeCode(code);
      let files: Record<string, string> = {
        "src/executor.js": EXECUTOR_SOURCE,
        "src/index.js": code,
      };
      if (package_json) {
        files["package.json"] = JSON.stringify(package_json);
      }
      let { mainModule, modules } = await createWorker({
        files,
        entryPoint: "src/executor.js",
        bundle: !!package_json,
      });
      let worker = env.LOADER.load({
        mainModule,
        modules,
        compatibilityDate: "2026-07-08",
        compatibilityFlags: ["nodejs_compat"],
        env: userEnv,
      });
      let response = await worker.getEntrypoint().fetch(
        new Request("https://executor/", {
          method: "POST",
          body: JSON.stringify({ variables, gooey_memory }),
        }),
      );
      return new Response(response.body, { status: response.status });
    } catch (e) {
      // Bundling errors (syntax errors, unresolved imports) and module
      // instantiation errors surface here instead of inside the dynamic
      // worker's fetch handler. The stack only contains our internal frames,
      // so report the message alone.
      return Response.json(
        {
          error: String(e),
          errorType: typeof e,
          logs: [],
          gooey_memory,
        },
        { status: 207 },
      );
    }
  },
} satisfies ExportedHandler<Env>;

// Recovers eval()-style completion-value semantics for bare scripts: if
// nothing is exported and the last top-level statement is an expression —
// a function, object, call, whatever — rewrite it to `export default (…);`
// so executor.js can import it (and call it, if it's a function).
function normalizeCode(code: string): string {
  let { body, hasExportDefault } = parseCode(code);
  if (hasExportDefault) {
    return code;
  }
  // Like in eval(), declarations yield no completion value, so the
  // script's value is the last expression statement before any trailing
  // (hoisted anyway) declarations.
  let last = body.findLast((node) => node.type === "ExpressionStatement");
  if (last) {
    let newCode =
      code.slice(0, last.start) +
      "export default (" +
      code.slice(last.expression.start, last.expression.end) +
      ");" +
      code.slice(last.end);
    if (parseCode(newCode).hasExportDefault) {
      return newCode;
    }
  }
  return code;
}

const ACORN_OPTIONS: Options = {
  ecmaVersion: "latest",
  sourceType: "module",
};

// Returns the normalized code only if it parses as a module containing
// the inserted default export; otherwise the original.
function parseCode(code: string) {
  try {
    let body = parse(code, ACORN_OPTIONS).body;
    let hasExportDefault = body.some(
      (node) => node.type === "ExportDefaultDeclaration",
    );
    return { body, hasExportDefault };
  } catch (e) {
    return { body: [], hasExportDefault: false };
  }
}

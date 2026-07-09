//
// Runs inside the Dynamic Worker: imports the user's module and invokes its
// default export with the provided variables. Console output is captured
// here by patching the console methods (see patchConsole below).
//
// This file is imported as a Text module (see rules in wrangler.jsonc) and
// bundled into each dynamic worker alongside the user's code — it never runs
// in the outer executor worker.
//

import { inspect } from "node:util";

export default {
  async fetch(request) {
    let { variables, gooey_memory } = await request.json();
    let logs = patchConsole();

    globalThis.GOOEY_MEMORY = gooey_memory;

    try {
      let module = await import("./index.js");
      let retval = module.default;
      if (typeof retval === "function") {
        retval = retval(variables);
      }
      retval = await retval;
      return Response.json({
        logs,
        retval,
        gooey_memory,
      });
    } catch (e) {
      return Response.json(
        {
          logs,
          error: inspect(e),
          errorType: typeof e,
          gooey_memory,
        },
        { status: 207 },
      );
    }
  },
};

function patchConsole() {
  let logs = [];
  function log(...args) {
    logs.push({ level: this, message: args.map(toString).join(" ") });
  }
  console.log = log.bind("log");
  console.warn = log.bind("warn");
  console.error = log.bind("error");
  console.info = log.bind("info");
  console.debug = log.bind("debug");
  console.trace = log.bind("trace");
  return logs;
}

function toString(obj) {
  if (typeof obj === "string") {
    return obj;
  } else {
    return inspect(obj);
  }
}

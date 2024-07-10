//
// To update this, run:
//    deployctl deploy --include functions/executor.js functions/executor.js --prod
// (Exclude --prod when testing in development)
//
Deno.serve(async (req) => {
  if (!isAuthenticated(req)) {
    return new Response("Unauthorized", { status: 401 });
  }

  let { tag, code, variables } = await req.json();
  let { mockConsole, logs } = captureConsole(tag);
  let status, response;

  try {
    let retval = isolatedEval(mockConsole, code, variables);
    if (retval instanceof Function) {
      retval = retval(variables);
    }
    if (retval instanceof Promise) {
      retval = await retval;
    }
    status = 200;
    response = { retval };
  } catch (e) {
    status = 500;
    response = { error: toString(e), errorType: typeof e };
  }

  let body = JSON.stringify({ ...response, logs });
  return new Response(body, { status });
});

function isolatedEval(console, code, variables) {
  // Hide global objects
  let Deno, global, self, globalThis, window;
  return eval(code);
}

function isAuthenticated(req) {
  let authorization = req.headers.get("Authorization");
  if (!authorization) return false;
  let parts = authorization.trim().split(" ");
  let token = parts[parts.length - 1];
  return token === Deno.env.get("GOOEY_AUTH_TOKEN");
}

function captureConsole(tag) {
  let logs = [];
  let prefix = `[${tag}]`;
  let realLog = console.log;
  let oldError = console.error;
  let mockConsole = {
    log(...args) {
      logs.push({ level: "log", message: args.map(toString).join(" ") });
      realLog(prefix, ...args);
    },
    error(...args) {
      logs.push({ level: "error", message: args.map(toString).join(" ") });
      oldError(prefix, ...args);
    },
  };
  return { mockConsole, logs };
}

function toString(obj) {
  if (typeof obj === "string") {
    return obj;
  } else {
    return Deno.inspect(obj);
  }
}

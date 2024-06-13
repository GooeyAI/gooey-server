Deno.serve(async (req) => {
  if (!isAuthenticated(req)) {
    return new Response("Unauthorized", { status: 401 });
  }

  let logs = captureConsole();
  let code = await req.json();
  let status, response;

  try {
    let Deno = undefined; // Deno should not available to user code
    let retval = eval(code);
    if (retval instanceof Function) {
      retval = retval();
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

function isAuthenticated(req) {
  let authorization = req.headers.get("Authorization");
  if (!authorization) return false;
  let parts = authorization.trim().split(" ");
  let token = parts[parts.length - 1];
  return token === Deno.env.get("GOOEY_AUTH_TOKEN");
}

function captureConsole() {
  let logs = [];

  let oldLog = console.log;
  console.log = (...args) => {
    logs.push({ level: "log", message: args.map(toString).join(" ") });
    oldLog(...args);
  };

  let oldError = console.error;
  console.error = (...args) => {
    logs.push({ level: "error", message: args.map(toString).join(" ") });
    oldError(...args);
  };

  return logs;
}

function toString(obj) {
  if (typeof obj === "string") {
    return obj;
  } else {
    return Deno.inspect(obj);
  }
}

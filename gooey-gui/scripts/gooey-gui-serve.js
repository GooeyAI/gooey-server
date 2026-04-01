#!/usr/bin/env node
let path = require("path");

let pkgPath = path.dirname(__dirname);
process.chdir(pkgPath);

console.log("Serving build from", pkgPath);

process.argv.push("build");
require("@remix-run/serve/dist/cli.js");

#!/usr/bin/env bash

set -ex

deployctl deploy --include function-executor.js function-executor.js

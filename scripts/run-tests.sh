#!/usr/bin/env bash

set -ex

echo "==> Downloading fixture.json..."
wget -N -nv https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/63fdbbbe-9fbf-11f0-9ffd-02420a000184/fixture.json

echo "==> Formatting with ruff..."
poetry run ruff format --diff .

echo "==> Running pytest..."
pytest $@

#!/usr/bin/env bash

set -ex

echo "==> Downloading fixture.json..."
wget -N -nv https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/237ffb72-9931-11f0-a655-02420a000109/fixture.json

echo "==> Formatting with ruff..."
poetry run ruff format --diff .

echo "==> Running pytest..."
pytest $@

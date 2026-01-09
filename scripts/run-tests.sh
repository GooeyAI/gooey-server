#!/usr/bin/env bash

set -ex

echo "==> Downloading fixture.json..."
wget -N -nv https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/f0769d1a-ed38-11f0-96f2-02420a0001b0/fixture.json

echo "==> Formatting with ruff..."
poetry run ruff format --diff .

echo "==> Running pytest..."
pytest $@

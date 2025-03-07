#!/usr/bin/env bash

set -ex

echo "==> Downloading fixture.json..."
wget -N -nv https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/177258a2-fadf-11ef-8ffe-02420a00013c/fixture.json

echo "==> Linting with black..."
black --check --diff .

echo "==> Running pytest..."
pytest $@

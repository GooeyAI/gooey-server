#!/usr/bin/env bash

set -ex

echo "==> Downloading fixture.json..."
wget -N -nv https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/b1f4d3b4-faf3-11ef-a62c-02420a00013c/fixture.json

echo "==> Linting with black..."
black --check --diff .

echo "==> Running pytest..."
pytest $@

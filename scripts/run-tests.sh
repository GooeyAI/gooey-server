#!/usr/bin/env bash

set -ex

echo "==> Downloading fixture.json..."
wget -N -nv https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/2f4f3e7c-e3bf-11ef-b200-02420a0001cf/fixture.json

echo "==> Linting with black..."
black --check --diff .

echo "==> Running pytest..."
pytest $@

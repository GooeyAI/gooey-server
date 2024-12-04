#!/usr/bin/env bash

set -ex

echo "==> Downloading fixture.json..."
wget -N -nv https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/9621533c-adce-11ef-b989-02420a00016f/fixture.json

echo "==> Linting with black..."
black --check --diff .

echo "==> Running pytest..."
pytest $@

#!/usr/bin/env bash

set -ex

echo "==> Downloading fixture.json..."
wget -N -nv https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/56a6de00-171b-11f0-a440-8e93953183bb/fixture.json

echo "==> Linting with black..."
black --check --diff .

echo "==> Running pytest..."
pytest $@

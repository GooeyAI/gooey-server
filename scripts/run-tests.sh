#!/usr/bin/env bash

echo "==> Downloading fixture.json..."
wget -N -nv https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/2268bf98-fab9-11ee-99a6-8e93953183bb/fixture.json

echo "==> Linting with black..."
black --check --diff .

echo "==> Running pytest..."
pytest

#!/usr/bin/env bash

echo "==> Downloading fixture.json..."
wget -N -nv https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/8972b298-1206-11ef-aac6-02420a00010c/fixture.json

echo "==> Linting with black..."
black --check --diff .

echo "==> Running pytest..."
pytest

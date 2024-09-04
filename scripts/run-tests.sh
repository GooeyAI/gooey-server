#!/usr/bin/env bash

echo "==> Downloading fixture.json..."
wget -N -nv https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/4f614770-446c-11ef-b36e-02420a000176/fixture.json

echo "==> Linting with black..."
black --check --diff .

echo "==> Running pytest..."
pytest

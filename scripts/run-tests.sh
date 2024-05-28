#!/usr/bin/env bash

echo "==> Downloading fixture.json..."
wget -N -nv https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/830efd3e-0848-11ef-b549-02420a000186/fixture.json

echo "==> Linting with black..."
black --check --diff .

echo "==> Running pytest..."
pytest

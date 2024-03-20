#!/usr/bin/env bash

echo "==> Downloading fixture.json..."
wget -c -nv https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/ca0f13b8-d6ed-11ee-870b-8e93953183bb/fixture.json

echo "==> Linting with black..."
black --check --diff .

echo "==> Running pytest..."
pytest

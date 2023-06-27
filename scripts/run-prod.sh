#!/usr/bin/env bash

set -ex

if [ "$DUMP_DATABASE" ] && [ "$PGDATABASE" ]; then
  dropdb $PGDATABASE || true
  createdb -T template0 $PGDATABASE
  pg_dump $DUMP_DATABASE | psql -q $PGDATABASE
fi

if [ "$RUN_JUPYTER" ]; then
  pip install jupyterlab
  jupyter lab --ip 0.0.0.0 --port 8000 --allow-root
elif [ "$RUN_DJANGO" ]; then
  ./manage.py migrate
  ./manage.py collectstatic
  SENTRY_ENVIRONMENT="django" gunicorn gooeysite.wsgi --bind 0.0.0.0:8000 --threads "${WEB_CONCURRENCY:-1}"
elif [ "$RUN_STREAMLIT" ]; then
  SENTRY_ENVIRONMENT="streamlit" streamlit run Home.py --server.address=0.0.0.0 --server.port=8000
else
  SENTRY_ENVIRONMENT="fastapi" uvicorn server:app --host 0.0.0.0 --port 8000
fi

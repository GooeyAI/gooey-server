#!/usr/bin/env bash

set -ex

if [ "$RUN_DJANGO" ]; then
  ./manage.py migrate
  ./manage.py collectstatic
  SENTRY_ENVIRONMENT="django" gunicorn gooeysite.wsgi --bind 0.0.0.0:8000 --threads ${WEB_CONCURRENCY:-1}
if [ "$RUN_STREAMLIT" ]; then
  SENTRY_ENVIRONMENT="streamlit" streamlit run Home.py --server.address=0.0.0.0 --server.port=8501
else
  SENTRY_ENVIRONMENT="fastapi" uvicorn server:app --host 0.0.0.0 --workers ${WEB_CONCURRENCY:-1} --port 8000
fi

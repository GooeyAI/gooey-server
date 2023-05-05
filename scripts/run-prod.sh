#!/usr/bin/env bash
set -ex
if [ "$RUN_DJANGO" ]; then
  ./manage.py migrate
  ./manage.py collectstatic
  SENTRY_ENVIRONMENT="django" gunicorn gooeysite.wsgi --bind 0.0.0.0:8000 --threads $WEB_CONCURRENCY
else
  SENTRY_ENVIRONMENT="streamlit" streamlit run Home.py --server.address=0.0.0.0 --server.port=8501 &
  SENTRY_ENVIRONMENT="fast-api" uvicorn server:app --host 0.0.0.0 --workers $WEB_CONCURRENCY --port 8000 &
  wait
fi

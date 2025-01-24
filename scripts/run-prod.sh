#!/usr/bin/env bash

set -ex

if [ "$RUN_JUPYTER" ]; then
  pip install jupyterlab
  jupyter lab --allow-root --ip 0.0.0.0 --port 8000
elif [ "$RUN_DJANGO" ]; then
  ./manage.py runscript setup_vespa_db
  ./manage.py migrate
  ./manage.py collectstatic
  ./manage.py runscript init_llm_pricing
  SENTRY_ENVIRONMENT="django" exec gunicorn gooeysite.wsgi --bind 0.0.0.0:8000 --threads "${MAX_THREADS:-1}" --access-logfile -
elif [ "$RUN_STREAMLIT" ]; then
  SENTRY_ENVIRONMENT="streamlit" exec streamlit run Home.py --server.address=0.0.0.0 --server.port=8000
elif [ "$RUN_CELERY" ]; then
  SENTRY_ENVIRONMENT="celery" exec celery -A celeryapp worker -l INFO -P prefork -c ${MAX_THREADS:-1} --max-tasks-per-child 1
elif [ "$RUN_CELERY_BEAT" ]; then
  SENTRY_ENVIRONMENT="celery" exec celery -A celeryapp beat -l INFO --max-interval 300
else
  SENTRY_ENVIRONMENT="fastapi" exec uvicorn server:app --host 0.0.0.0 --port 8000
fi

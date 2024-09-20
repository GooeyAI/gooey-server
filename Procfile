# this Procfile can be run with `honcho`, and it can start multiple processes
# with a single command. Handy for development. All of the below commands are
# setup to run in dev mode only, and not in prod.
#
# The assumptions here are that:
# - you have redis installed but not running as a background service
# - you have rabbitmq installed but not running as a background service
# - your local gooey-ui repo is at ../gooey-ui/
#
# You can comment any of the processes if you have background services running
# for them. You can also change the path for the `ui` process from `../gooey-ui/`
# to wherever your local gooey-ui directory is.

api: poetry run uvicorn server:app --host 127.0.0.1 --port 8080 --reload

admin: poetry run python manage.py runserver 127.0.0.1:8000

dashboard: poetry run streamlit run Home.py --server.port 8501 --server.headless true

celery: poetry run celery -A celeryapp worker -P threads -c 16 -l DEBUG

ui: cd ../gooey-gui/; PORT=3000 npm run dev

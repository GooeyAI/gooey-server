#!/usr/bin/env bash

set -ex

streamlit run Home.py --server.headless true --server.port 8501 &
python3 manage.py runserver 0.0.0.0:8000 &
uvicorn server:app --host 0.0.0.0 --port 8080 --reload &
wait

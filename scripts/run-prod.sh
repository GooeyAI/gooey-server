#!/usr/bin/env bash

SENTRY_ENVIRONMENT="streamlit" streamlit run Home.py --server.address=0.0.0.0 --server.port=8501 &
SENTRY_ENVIRONMENT="fast-api" uvicorn server:app --host 0.0.0.0 --port 8000 &
wait
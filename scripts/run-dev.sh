SENTRY_ENVIRONMENT="streamlit" streamlit run Home.py --server.headless true --server.port 8501 &
SENTRY_ENVIRONMENT="fast-api" uvicorn server:app --reload --port 8000 &
nginx -c $PWD/nginx.dev.conf &
wait
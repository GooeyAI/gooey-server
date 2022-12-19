streamlit run Home.py --server.headless true --server.port 8501 &
uvicorn server:app --reload --port 8000 &
nginx -c $PWD/nginx.dev.conf &
wait
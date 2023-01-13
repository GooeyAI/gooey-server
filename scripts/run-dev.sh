streamlit run Home.py --server.headless true --server.port 8501 &
uvicorn server:app --reload  --uds /tmp/uvicorn.sock --proxy-headers &
nginx -c $PWD/nginx.dev.conf &
wait
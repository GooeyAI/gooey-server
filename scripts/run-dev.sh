streamlit run Home.py \
  --client.showErrorDetails true \
  --server.enableXsrfProtection false \
  --server.headless true \
  --server.port 8501
python scripts/uvicorn_run_dev.py
nginx -c $PWD/nginx.dev.conf &
wait

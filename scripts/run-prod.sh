#!/usr/bin/env bash

if [ "$STREAMLIT_SERVER" ]; then
  streamlit run Home.py --server.address=0.0.0.0 --server.port=8000
fi

if [ "$API_SERVER" ]; then
  uvicorn server:app --host 0.0.0.0 --port 8000
fi

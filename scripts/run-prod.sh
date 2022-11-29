#!/usr/bin/env bash

streamlit run Home.py --server.address=0.0.0.0 --server.port=8501

uvicorn server:app --host 0.0.0.0 --port 8000

#!/usr/bin/env bash

uvicorn server:app --host 0.0.0.0 --port 8080 --reload

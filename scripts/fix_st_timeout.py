"""
In develepment: make sure to run after re-installing streamlit

$ pip uninstall -y streamlit && poetry install --with dev --sync && python scripts/fix_st_timeout.py
"""

import site
from pathlib import Path


site_packages = Path(site.getsitepackages()[0])
js_file = site_packages / f"streamlit/static/static/js/main.c6074f42.chunk.js"

txt = js_file.read_text()

PING_MINIMUM_RETRY_PERIOD_MS = "10e3"
PING_MAXIMUM_RETRY_PERIOD_MS = "60e3"

WEBSOCKET_TIMEOUT_MS = "10e3"

# https://github.com/streamlit/streamlit/blob/99b2977f07e3e3a0f09435c27e07df7642f6116c/frontend/src/lib/WebsocketConnection.tsx#L457
idx = 116300
txt = txt[:idx] + WEBSOCKET_TIMEOUT_MS + txt[idx + 3 :]

# https://github.com/streamlit/streamlit/blob/99b2977f07e3e3a0f09435c27e07df7642f6116c/frontend/src/lib/WebsocketConnection.tsx#L342
idx = 114436
txt = (
    txt[:idx]
    + f"{PING_MINIMUM_RETRY_PERIOD_MS},{PING_MAXIMUM_RETRY_PERIOD_MS}"
    + txt[idx + 7 :]
)

js_file.write_text(txt)

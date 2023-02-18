"""
In develepment: make sure to run after re-installing streamlit

$ pip uninstall -y streamlit && poetry install --with dev --sync && python scripts/fix_st_timeout.py
"""

import site
from pathlib import Path

site_packages = Path(site.getsitepackages()[0])
js_file = site_packages / "streamlit/static/static/js/main.ef6eee61.js"
print(js_file)

txt = js_file.read_text()

WEBSOCKET_TIMEOUT_MS = "10e3"

# https://github.com/streamlit/streamlit/blob/master/frontend/src/lib/WebsocketConnection.tsx#L457
txt = txt.replace("),1e3)", f"),{WEBSOCKET_TIMEOUT_MS})")

PING_MINIMUM_RETRY_PERIOD_MS = "10e3"
PING_MAXIMUM_RETRY_PERIOD_MS = "60e3"

# https://github.com/streamlit/streamlit/blob/master/frontend/src/lib/WebsocketConnection.tsx#L342
txt = txt.replace(
    ",500,6e4,", f",{PING_MINIMUM_RETRY_PERIOD_MS},{PING_MAXIMUM_RETRY_PERIOD_MS},"
)

js_file.write_text(txt)

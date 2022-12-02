import site
from pathlib import Path


site_packages = Path(site.getsitepackages()[0])
js_file = site_packages / f"streamlit/static/static/js/main.c6074f42.chunk.js"

txt = js_file.read_text()

# Timeout fired after cancellation
idx = 116300
txt = txt[:idx] + "1e4" + txt[idx + 3 :]

# ,500
idx = 114436
txt = txt[:idx] + "1000" + txt[idx + 3 :]

js_file.write_text(txt)

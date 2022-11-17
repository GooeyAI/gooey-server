import site
from pathlib import Path

idx = 115567

site_packages = Path(site.getsitepackages()[0])
js_file = site_packages / f"streamlit/static/static/js/main.6569bfa5.chunk.js"

txt = js_file.read_text()
txt = txt[:idx] + "1e4" + txt[idx + 3 :]

js_file.write_text(txt)

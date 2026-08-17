from decouple import config

# where this gateway is served from (used in absolute redirects)
COMFY_BASE_URL = config("COMFY_BASE_URL", "http://localhost:8501")

# the main gooey.ai app (browser-facing; hosts /comfy/sso/)
GOOEY_APP_BASE_URL = config("GOOEY_APP_BASE_URL", "https://gooey.ai")
# the gooey-server API host (server-to-server; hosts /__/comfy/api/*)
GOOEY_API_BASE_URL = config("GOOEY_API_BASE_URL", "https://api.gooey.ai")
# shared bearer token — must match COMFY_SERVICE_TOKEN on gooey-server
COMFY_SERVICE_TOKEN = config("COMFY_SERVICE_TOKEN")

# signs the gateway's own session cookie
SECRET_KEY = config("SECRET_KEY")
SESSION_COOKIE = "comfy_session"
SESSION_MAX_AGE = 14 * 24 * 60 * 60

# "modal"  — per-workspace Modal sandboxes (production)
# "local"  — per-workspace local ComfyUI subprocesses via comfy-cli, using the
#            local GPU if present (local installs that don't want Modal)
# "static" — one fixed upstream ComfyUI shared by everyone
COMFY_BACKEND = config("COMFY_BACKEND", "modal")
STATIC_COMFY_URL = config("STATIC_COMFY_URL", "http://localhost:8188")
MODAL_GPU = config("MODAL_GPU", "L4")

# local backend: where per-workspace models/outputs live, first port to
# allocate, and whether to meter credits (off by default — own hardware)
COMFY_LOCAL_DATA_DIR = config("COMFY_LOCAL_DATA_DIR", "~/.gooey-comfy")
COMFY_LOCAL_PORT_START = config("COMFY_LOCAL_PORT_START", 8190, cast=int)
COMFY_LOCAL_BILLING = config("COMFY_LOCAL_BILLING", False, cast=bool)

# stop a workspace's instance after this much time with no proxy traffic
IDLE_TIMEOUT_SECONDS = config("IDLE_TIMEOUT_SECONDS", 15 * 60, cast=int)
# refuse to launch an instance if the workspace balance is below this
MIN_CREDITS_TO_LAUNCH = config("MIN_CREDITS_TO_LAUNCH", 10, cast=int)

GOOEY_LOGO_IMG_WHITE = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/ea26bc06-7eda-11ef-89fa-02420a0001f6/gooey-white-logo.png"

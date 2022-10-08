import os

import firebase_admin
from decouple import config, UndefinedValueError

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

GOOGLE_APPLICATION_CREDENTIALS = os.path.join(BASE_DIR, "serviceAccountKey.json")
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = GOOGLE_APPLICATION_CREDENTIALS

# load google app credentials from env var if available
try:
    _json = config("GOOGLE_APPLICATION_CREDENTIALS_JSON")
except UndefinedValueError:
    pass
else:
    with open(GOOGLE_APPLICATION_CREDENTIALS, "w") as f:
        f.write(_json)

os.environ["REPLICATE_API_TOKEN"] = config("REPLICATE_API_TOKEN", None)

if not firebase_admin._apps:
    firebase_admin.initialize_app()

GS_BUCKET_NAME = config("GS_BUCKET_NAME")
DARS_API_ROOT = config("DARS_API_ROOT", "https://api.daras.ai")

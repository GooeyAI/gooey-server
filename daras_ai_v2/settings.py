import os

import firebase_admin
from decouple import config, UndefinedValueError
from google.oauth2 import service_account

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
API_SECRET_KEY = config("API_SECRET_KEY", None)
GOOGLE_CLIENT_ID = config("GOOGLE_CLIENT_ID")
UBERDUCK_KEY = config("UBERDUCK_KEY")
UBERDUCK_SECRET = config("UBERDUCK_SECRET")
google_service_account_credentials = (
    service_account.Credentials.from_service_account_file("serviceAccountKey.json")
)

OPENAI_API_KEY = config("OPENAI_API_KEY")
DEBUG = True
if DEBUG:
    BASE_URL = "http://localhost:8501"
else:
    BASE_URL = "http://app.gooey.ai"

POSTMARK_API_TOKEN = config("POSTMARK_API_TOKEN")

import os

import firebase_admin
from decouple import config, UndefinedValueError, Csv
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

SECRET_KEY = config("SECRET_KEY")

APP_SECRET_KEY = config("APP_SECRET_KEY")
API_SECRET_KEY = config("API_SECRET_KEY")

GS_BUCKET_NAME = config("GS_BUCKET_NAME")
GOOGLE_CLIENT_ID = config("GOOGLE_CLIENT_ID")
UBERDUCK_KEY = config("UBERDUCK_KEY")
UBERDUCK_SECRET = config("UBERDUCK_SECRET")
google_service_account_credentials = (
    service_account.Credentials.from_service_account_file("serviceAccountKey.json")
)

OPENAI_API_KEY = config("OPENAI_API_KEY")

POSTMARK_API_TOKEN = config("POSTMARK_API_TOKEN")

APP_BASE_URL = config("APP_BASE_URL")
API_BASE_URL = config("API_BASE_URL")
IFRAME_BASE_URL = config("IFRAME_BASE_URL")

GPU_SERVER_1 = config("GPU_SERVER_1", "http://gpu-1.gooey.ai")
GPU_SERVER_2 = config("GPU_SERVER_2", "http://gpu-2.gooey.ai")

SCALESERP_API_KEY = config("SCALESERP_API_KEY", None)

# timeout for fetching external urls in the wild
EXTERNAL_REQUEST_TIMEOUT_SEC = config("EXTERNAL_REQUEST_TIMEOUT_SEC", 10)

ADMIN_EMAILS = config("ADMIN_EMAILS", cast=Csv(), default="sean@dara.network")

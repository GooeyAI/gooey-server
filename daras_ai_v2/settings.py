import os

import firebase_admin
import sentry_sdk
import stripe
from decouple import config, UndefinedValueError, Csv
from furl import furl
from sentry_sdk.integrations.threading import ThreadingIntegration
from starlette.templating import Jinja2Templates

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

GOOGLE_APPLICATION_CREDENTIALS = os.path.join(BASE_DIR, "serviceAccountKey.json")
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = GOOGLE_APPLICATION_CREDENTIALS
DEBUG = config("DEBUG", cast=bool)

if not DEBUG:
    sentry_sdk.init(
        dsn=config("SENTRY_DSN"),
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for performance monitoring.
        # We recommend adjusting this value in production.
        traces_sample_rate=0.01,
        send_default_pii=True,
        integrations=[
            ThreadingIntegration(propagate_hub=True),
        ],
    )

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

GS_BUCKET_NAME = config("GS_BUCKET_NAME")
GOOGLE_CLIENT_ID = config("GOOGLE_CLIENT_ID")
UBERDUCK_KEY = config("UBERDUCK_KEY")
UBERDUCK_SECRET = config("UBERDUCK_SECRET")

OPENAI_API_KEY = config("OPENAI_API_KEY")

POSTMARK_API_TOKEN = config("POSTMARK_API_TOKEN")

APP_BASE_URL = config("APP_BASE_URL", "/")
API_BASE_URL = config("API_BASE_URL", "/")
EXPLORE_URL = furl(APP_BASE_URL).add(path="explore").url
IFRAME_BASE_URL = config("IFRAME_BASE_URL", "/__/st/")

GPU_SERVER_1 = furl(config("GPU_SERVER_1", "http://gpu-1.gooey.ai"))
GPU_SERVER_2 = furl(config("GPU_SERVER_2", "http://gpu-2.gooey.ai"))

SCALESERP_API_KEY = config("SCALESERP_API_KEY", None)

# timeout for fetching external urls in the wild
EXTERNAL_REQUEST_TIMEOUT_SEC = config("EXTERNAL_REQUEST_TIMEOUT_SEC", 10)

ADMIN_EMAILS = config("ADMIN_EMAILS", cast=Csv(), default="sean@dara.network")

SUPPORT_EMAIL = "Gooey.AI Support <support@gooey.ai>"

CREDITS_TO_DEDUCT_PER_RUN = config("CREDITS_TO_DEDUCT_PER_RUN", 5, cast=int)
ANON_USER_FREE_CREDITS = config("ANON_USER_FREE_CREDITS", 25, cast=int)
LOGIN_USER_FREE_CREDITS = config("LOGIN_USER_FREE_CREDITS", 1000, cast=int)

stripe.api_key = config("STRIPE_SECRET_KEY", None)
STRIPE_ENDPOINT_SECRET = config("STRIPE_ENDPOINT_SECRET", None)

WIX_SITE_URL = config("WIX_SITE_URL", "https://www.help.gooey.ai")

DISCORD_INVITE_URL = "https://discord.gg/7C84UyzVDg"
GRANT_URL = "https://forms.gle/asc3SAzvh1nMj5fq5"

SEON_API_KEY = config("SEON_API_KEY", None)

templates = Jinja2Templates(directory="templates")

FB_APP_ID = config("FB_APP_ID", "")
FB_APP_SECRET = config("FB_APP_SECRET", "")
FB_WEBHOOK_TOKEN = config("FB_WEBHOOK_TOKEN", "")
WHATSAPP_ACCESS_TOKEN = config("WHATSAPP_ACCESS_TOKEN", None)

TALK_JS_APP_ID = config("TALK_JS_APP_ID", "")
TALK_JS_SECRET_KEY = config("TALK_JS_SECRET_KEY", "")

REDIS_URL = config("REDIS_URL", "redis://localhost:6379")
TWITTER_BEARER_TOKEN = config("TWITTER_BEARER_TOKEN", None)

PINECONE_API_KEY = config("PINECONE_API_KEY", "")
PINECONE_ENVIRONMENT = config("PINECONE_ENVIRONMENT", "us-east1-gcp")

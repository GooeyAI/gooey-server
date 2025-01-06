"""
Django settings for mysite project.

Generated by 'django-admin startproject' using Django 4.2.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/4.2/ref/settings/
"""

import datetime
import os
from pathlib import Path

import sentry_sdk
import stripe
from decouple import config, UndefinedValueError, Csv
from django.contrib.humanize.templatetags import humanize
from furl import furl
from sentry_sdk.integrations.threading import ThreadingIntegration
from starlette.templating import Jinja2Templates

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = config("DEBUG", cast=bool, default=True)

if DEBUG:
    SECRET_KEY = "xxxx"
else:
    SECRET_KEY = config("SECRET_KEY")

# https://hashids.org/
HASHIDS_URL_SALT = config("HASHIDS_URL_SALT", default="")  # used for the url shortener
HASHIDS_API_SALT = config("HASHIDS_API_SALT", default="")  # for everything else

ALLOWED_HOSTS = ["*"]
INTERNAL_IPS = ["127.0.0.1", "localhost"]
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = config("SECURE_HSTS_SECONDS", cast=int, default=0)
CSRF_COOKIE_HTTPONLY = config("CSRF_COOKIE_HTTPONLY", cast=bool, default=False)
CSRF_COOKIE_SECURE = config("CSRF_COOKIE_SECURE", cast=bool, default=False)
SESSION_COOKIE_SECURE = config("SESSION_COOKIE_SECURE", cast=bool, default=not DEBUG)

# CSP settings
CSP_DEFAULT_SRC = ("*",)

# Application definition

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "bots",
    "django_extensions",
    # "debug_toolbar",
    # the order matters, since we want to override the admin templates
    "django.forms",  # needed to override admin forms
    "django.contrib.admin",
    "safedelete",
    "app_users",
    "files",
    "url_shortener",
    "glossary_resources",
    "usage_costs",
    "embeddings",
    "handles",
    "payments",
    "functions",
    "workspaces",
    "api_keys",
    "managed_secrets",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "csp.middleware.CSPMiddleware",
    # "debug_toolbar.middleware.DebugToolbarMiddleware",
]

ROOT_URLCONF = "gooeysite.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

templates = Jinja2Templates(directory="templates")
templates.env.globals.update(
    dict(humanize=humanize, datetime=datetime, settings=globals())
)


# needed to override django admin templates
FORM_RENDERER = "django.forms.renderers.TemplatesSetting"

WSGI_APPLICATION = "gooeysite.wsgi.application"


# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases
try:
    PGHOST = config("PGHOST")
    PGPORT = config("PGPORT")
    PGDATABASE = config("PGDATABASE")
    PGUSER = config("PGUSER")
    PGPASSWORD = config("PGPASSWORD")
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": PGDATABASE,
            "USER": PGUSER,
            "PASSWORD": PGPASSWORD,
            "HOST": PGHOST,
            "PORT": PGPORT,
            "CONN_HEALTH_CHECKS": True,
            "CONN_MAX_AGE": None,
            # https://docs.djangoproject.com/en/5.1/ref/databases/#server-side-cursors
            "DISABLE_SERVER_SIDE_CURSORS": config(
                "DISABLE_SERVER_SIDE_CURSORS", cast=bool, default=False
            ),
        }
    }
except UndefinedValueError:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "Asia/Kolkata"

USE_I18N = True

USE_TZ = True

DATETIME_FORMAT = "N j, D, Y, h:i:s A"

from django.conf.locale.en import formats as es_formats

es_formats.DATETIME_FORMAT = DATETIME_FORMAT

SHORT_DATETIME_FORMAT = "%b %d, %Y %-I:%M %p"

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.2/howto/static-files/

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

if not DEBUG:
    LOGGING = {
        "version": 1,
        "disable_existing_loggers": False,
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
            },
        },
        "root": {
            "handlers": ["console"],
        },
    }

# Gooey settings
#

if not DEBUG:
    sentry_sdk.init(
        dsn=config("SENTRY_DSN"),
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for performance monitoring.
        # We recommend adjusting this value in production.
        traces_sample_rate=0.005,
        send_default_pii=True,
        integrations=[
            ThreadingIntegration(propagate_hub=True),
        ],
    )

service_account_key_path = str(BASE_DIR / "serviceAccountKey.json")
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = service_account_key_path
# save json file from env var if available
try:
    _json = config("GOOGLE_APPLICATION_CREDENTIALS_JSON")
except UndefinedValueError:
    pass
else:
    with open(service_account_key_path, "w") as f:
        f.write(_json)

import firebase_admin

if not firebase_admin._apps:
    firebase_admin.initialize_app()

GOOEY_LOGO_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/2a3aacb4-0941-11ee-b236-02420a0001fb/thumbs/logo%20black.png_400x400.png"
GOOEY_LOGO_IMG_WHITE = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/ea26bc06-7eda-11ef-89fa-02420a0001f6/gooey-white-logo.png"
GOOEY_LOGO_RECT = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/d628be8a-9207-11ef-8aee-02420a000186/984x272%20rect%20gooey%20logo.png"

os.environ["REPLICATE_API_TOKEN"] = config("REPLICATE_API_TOKEN", default="")

GCP_PROJECT = config("GCP_PROJECT", default="dara-c1b52")
GCP_REGION = config("GCP_REGION", default="us-central1")

GS_BUCKET_NAME = config("GS_BUCKET_NAME", default=f"{GCP_PROJECT}.appspot.com")
GS_MEDIA_PATH = config("GS_MEDIA_PATH", default="daras_ai/media")
GS_STATIC_PATH = config("GS_STATIC_PATH", default="gooeyai/static")


GOOGLE_CLIENT_ID = config("GOOGLE_CLIENT_ID", default="")
FIREBASE_CONFIG = config("FIREBASE_CONFIG", default="")

UBERDUCK_KEY = config("UBERDUCK_KEY", None)
UBERDUCK_SECRET = config("UBERDUCK_SECRET", None)

OPENAI_API_KEY = config("OPENAI_API_KEY", default="")
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

GROQ_API_KEY = config("GROQ_API_KEY", default="")

REPLICATE_API_KEY = config("REPLICATE_API_KEY", default="")
TOGETHER_API_KEY = config("TOGETHER_API_KEY", default="")
FAL_API_KEY = config("FAL_API_KEY", default="")

APP_BASE_URL: str = config("APP_BASE_URL", "/")  # type: ignore
API_BASE_URL = config("API_BASE_URL", "/")
ADMIN_BASE_URL = config("ADMIN_BASE_URL", "https://admin.gooey.ai/")
EXPLORE_URL = furl(APP_BASE_URL).add(path="explore").url
PRICING_DETAILS_URL = furl(APP_BASE_URL).add(path="pricing").url
DOCS_URL = config("DOCS_URL", "https://docs.gooey.ai")
BLOG_URL = config("BLOG_URL", "https://blog.gooey.ai")
CONTACT_URL = config("CONTACT_URL", "https://www.help.gooey.ai/contact")

HEADER_LINKS = [
    ("/explore/", "Explore"),
    (DOCS_URL, "Docs"),
    ("/api/", "API"),
    (BLOG_URL, "Blog"),
    ("/pricing", "Pricing"),
    (CONTACT_URL, "Contact"),
]

GPU_SERVER_1 = furl(config("GPU_SERVER_1", "http://gpu-1.gooey.ai"))

SERPER_API_KEY = config("SERPER_API_KEY", None)

# timeout for fetching external urls in the wild
EXTERNAL_REQUEST_TIMEOUT_SEC = config("EXTERNAL_REQUEST_TIMEOUT_SEC", 10)


POSTMARK_API_TOKEN = config("POSTMARK_API_TOKEN", None)
ADMIN_EMAILS = config("ADMIN_EMAILS", cast=Csv(), default="")
ADMINS = [("Devs", "devs+django@gooey.ai")]
SUPPORT_EMAIL = "Gooey.AI Support <support@gooey.ai>"
SALES_EMAIL = "Gooey.AI Sales <sales@gooey.ai>"
PAYMENT_EMAIL = "Gooey.AI Payments <payment-support@gooey.ai>"
SEND_RUN_EMAIL_AFTER_SEC = config("SEND_RUN_EMAIL_AFTER_SEC", 5)

DISALLOWED_TITLE_SLUGS = config("DISALLOWED_TITLE_SLUGS", cast=Csv(), default="") + [
    # tab names
    "api",
    "examples",
    "history",
    "saved",
    "integrations",
    # other
    "docs",
]

SAFETY_CHECKER_EXAMPLE_ID = config("SAFETY_CHECKER_EXAMPLE_ID", "3rcxqx0r")
SAFETY_CHECKER_BILLING_EMAIL = config(
    "SAFETY_CHECKER_BILLING_EMAIL", "support+mods@gooey.ai"
)

INTEGRATION_DETAILS_GENERATOR_EXAMPLE_ID = config(
    "INTEGRATION_DETAILS_GENERATOR_EXAMPLE_ID", "59yem9i3iet5"
)

CREDITS_TO_DEDUCT_PER_RUN = config("CREDITS_TO_DEDUCT_PER_RUN", 5, cast=int)

ANON_USER_FREE_CREDITS = config("ANON_USER_FREE_CREDITS", 25, cast=int)
VERIFIED_EMAIL_USER_FREE_CREDITS = config(
    "VERIFIED_EMAIL_USER_FREE_CREDITS", 500, cast=int
)
VERIFIED_EMAIL_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "outlook.com",
    "hotmail.com",
    "live.com",
    "icloud.com",
    "me.com",
    "zohomail.com",
}
FIRST_WORKSPACE_FREE_CREDITS = config("WORKSPACE_FREE_CREDITS", 500, cast=int)

ADDON_CREDITS_PER_DOLLAR = config("ADDON_CREDITS_PER_DOLLAR", 100, cast=int)
ADDON_AMOUNT_CHOICES = [10, 30, 50, 100, 300, 500, 1000]  # USD
AUTO_RECHARGE_BALANCE_THRESHOLD_CHOICES = [300, 1000, 3000, 10000]  # Credit balance
AUTO_RECHARGE_COOLDOWN_SECONDS = config("AUTO_RECHARGE_COOLDOWN_SECONDS", 60, cast=int)

LOW_BALANCE_EMAIL_CREDITS = config("LOW_BALANCE_EMAIL_CREDITS", 200, cast=int)
LOW_BALANCE_EMAIL_DAYS = config("LOW_BALANCE_EMAIL_DAYS", 7, cast=int)
LOW_BALANCE_EMAIL_ENABLED = config("LOW_BALANCE_EMAIL_ENABLED", True, cast=bool)

STRIPE_SECRET_KEY = config("STRIPE_SECRET_KEY", None)
STRIPE_ENDPOINT_SECRET = config("STRIPE_ENDPOINT_SECRET", None)
stripe.api_key = STRIPE_SECRET_KEY

STRIPE_USER_SUBSCRIPTION_METADATA_FIELD: str = "subscription_key"
STRIPE_ADDON_PRODUCT_NAME = config(
    "STRIPE_ADDON_PRODUCT_NAME", "Gooey.AI Add-on Credits"
)

PAYPAL_CLIENT_ID = config("PAYPAL_CLIENT_ID", "")
PAYPAL_SECRET = config("PAYPAL_SECRET", "")
PAYPAL_BASE: str = config("PAYPAL_BASE", "")  # type: ignore
PAYPAL_WEB_BASE_URL: furl = config("PAYPAL_WEB_BASE_URL", "https://www.paypal.com", cast=furl)  # type: ignore
PAYPAL_WEBHOOK_ID: str = config("PAYPAL_WEBHOOK_ID", "")  # type: ignore
PAYPAL_DEFAULT_PRODUCT_NAME: str = config("PAYPAL_DEFAULT_PRODUCT_NAME", "Gooey.AI Credits")  # type: ignore

WIX_SITE_URL = config("WIX_SITE_URL", "https://www.help.gooey.ai")

DISCORD_INVITE_URL = "https://discord.gg/7C84UyzVDg"
GRANT_URL = "https://forms.gle/asc3SAzvh1nMj5fq5"

APOLLO_API_KEY = config("APOLLO_API_KEY", None)

FB_APP_ID = config("FB_APP_ID", "")
FB_APP_SECRET = config("FB_APP_SECRET", "")
FB_WEBHOOK_TOKEN = config("FB_WEBHOOK_TOKEN", "")
FB_WHATSAPP_CONFIG_ID = config("FB_WHATSAPP_CONFIG_ID", "")
WHATSAPP_2FA_PIN = config("WHATSAPP_2FA_PIN", "190604")
WHATSAPP_ACCESS_TOKEN = config("WHATSAPP_ACCESS_TOKEN", None)
SLACK_VERIFICATION_TOKEN = config("SLACK_VERIFICATION_TOKEN", "")
SLACK_CLIENT_ID = config("SLACK_CLIENT_ID", "")
SLACK_CLIENT_SECRET = config("SLACK_CLIENT_SECRET", "")

TALK_JS_APP_ID = config("TALK_JS_APP_ID", "")
TALK_JS_SECRET_KEY = config("TALK_JS_SECRET_KEY", "")

REDIS_URL = config("REDIS_URL", "redis://localhost:6379")
# redis configured as cache backend
REDIS_CACHE_URL = config("REDIS_CACHE_URL", "redis://localhost:6379")
TWITTER_BEARER_TOKEN = config("TWITTER_BEARER_TOKEN", None)

REDIS_MODELS_CACHE_EXPIRY = 60 * 60 * 24 * 7

GPU_CELERY_BROKER_URL = config("GPU_CELERY_BROKER_URL", "amqp://localhost:5674")
GPU_CELERY_RESULT_BACKEND = config(
    "GPU_CELERY_RESULT_BACKEND", "redis://localhost:6374"
)

LOCAL_CELERY_BROKER_URL = config("LOCAL_CELERY_BROKER_URL", "amqp://")
LOCAL_CELERY_RESULT_BACKEND = config("LOCAL_CELERY_RESULT_BACKEND", REDIS_URL)

AZURE_FORM_RECOGNIZER_ENDPOINT = config("AZURE_FORM_RECOGNIZER_ENDPOINT", "")
AZURE_FORM_RECOGNIZER_KEY = config("AZURE_FORM_RECOGNIZER_KEY", "")

AZURE_IMAGE_MODERATION_ENDPOINT = config("AZURE_IMAGE_MODERATION_ENDPOINT", "")
AZURE_IMAGE_MODERATION_KEY = config("AZURE_IMAGE_MODERATION_KEY", "")

AZURE_SPEECH_REGION = config("AZURE_SPEECH_REGION", "")
AZURE_SPEECH_KEY = config("AZURE_SPEECH_KEY", "")
AZURE_SPEECH_ENDPOINT = f"https://{AZURE_SPEECH_REGION}.api.cognitive.microsoft.com"
AZURE_TTS_ENDPOINT = f"https://{AZURE_SPEECH_REGION}.tts.speech.microsoft.com"

AZURE_KEY_VAULT_ENDPOINT = config("AZURE_KEY_VAULT_ENDPOINT", "")

AZURE_OPENAI_ENDPOINT_CA = config("AZURE_OPENAI_ENDPOINT_CA", "")
AZURE_OPENAI_KEY_CA = config("AZURE_OPENAI_KEY_CA", "")
AZURE_OPENAI_ENDPOINT_EASTUS2 = config("AZURE_OPENAI_ENDPOINT_EASTUS2", "")
AZURE_OPENAI_KEY_EASTUS2 = config("AZURE_OPENAI_KEY_EASTUS2", "")

DEEPGRAM_API_KEY = config("DEEPGRAM_API_KEY", "")

ELEVEN_LABS_API_KEY = config("ELEVEN_LABS_API_KEY", "")

GHANA_NLP_SUBKEY = config("GHANA_NLP_SUBKEY", "")

VESPA_URL = config("VESPA_URL", "http://localhost:8085")
VESPA_CONFIG_SERVER_URL = config("VESPA_CONFIG_SERVER_URL", "http://localhost:19071")
VESPA_SCHEMA = config("VESPA_SCHEMA", "gooey")

ANTHROPIC_API_KEY = config("ANTHROPIC_API_KEY", "")
os.environ["ANTHROPIC_API_KEY"] = ANTHROPIC_API_KEY

WEB_WIDGET_LIB = config(
    "WEB_WIDGET_LIB",
    "https://cdn.jsdelivr.net/gh/GooeyAI/gooey-web-widget@2/dist/lib.js",
)

MAX_CONCURRENCY_ANON = config("MAX_CONCURRENCY_ANON", 1, cast=int)
MAX_CONCURRENCY_FREE = config("MAX_CONCURRENCY_FREE", 2, cast=int)
MAX_CONCURRENCY_PAID = config("MAX_CONCURRENCY_PAID", 4, cast=int)

MAX_RPM_ANON = config("MAX_RPM_ANON", 3, cast=int)
MAX_RPM_FREE = config("MAX_RPM_FREE", 6, cast=int)
MAX_RPM_PAID = config("MAX_RPM_PAID", 10, cast=int)

DENO_FUNCTIONS_AUTH_TOKEN = config("DENO_FUNCTIONS_AUTH_TOKEN", "")
DENO_FUNCTIONS_URL = config("DENO_FUNCTIONS_URL", "")

TWILIO_ACCOUNT_SID = config("TWILIO_ACCOUNT_SID", "")
TWILIO_API_KEY_SID = config("TWILIO_API_KEY_SID", "")
TWILIO_API_KEY_SECRET = config("TWILIO_API_KEY_SECRET", "")

WORKSPACE_INVITE_EXPIRY_DAYS = config("WORKSPACE_INVITE_EXPIRY_DAYS", 180, cast=int)
WORKSPACE_INVITE_EMAIL_COOLDOWN_INTERVAL = config(
    "WORKSPACE_INVITE_EMAIL_COOLDOWN_INTERVAL", 60 * 60 * 24, cast=int  # 24 hours
)

SCRAPING_PROXY_HOST = config("SCRAPING_PROXY_HOST", "")
SCRAPING_PROXY_USERNAME = config("SCRAPING_PROXY_USERNAME", "")
SCRAPING_PROXY_PASSWORD = config("SCRAPING_PROXY_PASSWORD", "")
SCRAPING_PROXY_CERT_URL = config("SCRAPING_PROXY_CERT_URL", "")

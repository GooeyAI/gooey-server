"""
Django settings for mysite project.

Generated by 'django-admin startproject' using Django 4.2.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/4.2/ref/settings/
"""

import os
from pathlib import Path

import sentry_sdk
import stripe
from decouple import config, UndefinedValueError, Csv
from furl import furl
from sentry_sdk.integrations.threading import ThreadingIntegration
from starlette.templating import Jinja2Templates

from django.contrib.humanize.templatetags import humanize

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = config("DEBUG", cast=bool, default=True)

if DEBUG:
    SECRET_KEY = "xxxx"
else:
    SECRET_KEY = config("SECRET_KEY")

# https://hashids.org/
HASHIDS_SALT = config("HASHIDS_SALT", default="")

ALLOWED_HOSTS = ["*"]
INTERNAL_IPS = ["127.0.0.1"]
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Application definition

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "bots",
    "django_extensions",
    # the order matters, since we want to override the admin templates
    "django.forms",  # needed to override admin forms
    "django.contrib.admin",
    "app_users",
    "url_shortener",
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
templates.env.globals["humanize"] = humanize


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

# Gooey settings
#

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

os.environ["REPLICATE_API_TOKEN"] = config("REPLICATE_API_TOKEN", default="")

GS_BUCKET_NAME = config("GS_BUCKET_NAME", default="")
# GOOGLE_CLIENT_ID = config("GOOGLE_CLIENT_ID")
UBERDUCK_KEY = config("UBERDUCK_KEY", None)
UBERDUCK_SECRET = config("UBERDUCK_SECRET", None)

OPENAI_API_KEY = config("OPENAI_API_KEY", default="")
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY
REPLICATE_API_KEY = config("REPLICATE_API_KEY", default="")
TOGETHER_API_KEY = config("TOGETHER_API_KEY", default="")

POSTMARK_API_TOKEN = config("POSTMARK_API_TOKEN", None)

APP_BASE_URL = config("APP_BASE_URL", "/")
API_BASE_URL = config("API_BASE_URL", "/")
EXPLORE_URL = furl(APP_BASE_URL).add(path="explore").url

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

FB_APP_ID = config("FB_APP_ID", "")
FB_APP_SECRET = config("FB_APP_SECRET", "")
FB_WEBHOOK_TOKEN = config("FB_WEBHOOK_TOKEN", "")
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

GPU_CELERY_BROKER_URL = config("GPU_CELERY_BROKER_URL", "amqp://localhost:5674")
GPU_CELERY_RESULT_BACKEND = config(
    "GPU_CELERY_RESULT_BACKEND", "redis://localhost:6374"
)

LOCAL_CELERY_BROKER_URL = config("LOCAL_CELERY_BROKER_URL", "amqp://")
LOCAL_CELERY_RESULT_BACKEND = config("LOCAL_CELERY_RESULT_BACKEND", REDIS_URL)

AZURE_FORM_RECOGNIZER_ENDPOINT = config("AZURE_FORM_RECOGNIZER_ENDPOINT")
AZURE_FORM_RECOGNIZER_KEY = config("AZURE_FORM_RECOGNIZER_KEY")

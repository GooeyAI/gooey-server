# Configuration Reference

All settings are read from environment variables (or a `.env` file).

---

## Server URLs

| Variable         | Required | Default                   | Description                                               |
| ---------------- | -------- | ------------------------- | --------------------------------------------------------- |
| `APP_BASE_URL`   | No       | `http://localhost:3000`   | Public base URL of the frontend (e.g. `https://gooey.ai`) |
| `API_BASE_URL`   | No       | `http://localhost:8080`   | Public base URL of the API server                         |
| `ADMIN_BASE_URL` | No       | `https://admin.gooey.ai/` | Public base URL of the Django admin site                  |

---

## Django

| Variable                | Required      | Default        | Description                                                          |
| ----------------------- | ------------- | -------------- | -------------------------------------------------------------------- |
| `DEBUG`                 | No            | `True`         | Enable Django debug mode. Set to `False` in production.              |
| `SECRET_KEY`            | **Prod only** | `"xxxx"` (dev) | Django secret key. Must be a strong random value when `DEBUG=False`. |
| `SENTRY_DSN`            | No            | —              | Sentry error reporting DSN. Works only when `DEBUG=False`.           |
| `SECURE_HSTS_SECONDS`   | No            | `0`            | HSTS max-age in seconds. Set to a non-zero value in production.      |
| `SESSION_COOKIE_SECURE` | No            | `not DEBUG`    | Require HTTPS for session cookies.                                   |

---

## Database (PostgreSQL)

If none of these are set, the server falls back to SQLite (suitable for development only).

| Variable     | Required       | Description            |
| ------------ | -------------- | ---------------------- |
| `PGHOST`     | For PostgreSQL | Postgres host          |
| `PGPORT`     | For PostgreSQL | Postgres port          |
| `PGUSER`     | For PostgreSQL | Postgres user          |
| `PGDATABASE` | For PostgreSQL | Postgres database name |
| `PGPASSWORD` | For PostgreSQL | Postgres password      |

---

## Redis / Celery

| Variable                      | Required | Default                  | Description                                         |
| ----------------------------- | -------- | ------------------------ | --------------------------------------------------- |
| `REDIS_URL`                   | No       | `redis://localhost:6379` | Redis URL used for session/cache and Celery results |
| `REDIS_CACHE_URL`             | No       | `redis://localhost:6379` | Redis URL used as Django cache backend              |
| `LOCAL_CELERY_BROKER_URL`     | No       | `amqp://`                | RabbitMQ URL for the local Celery worker            |
| `LOCAL_CELERY_RESULT_BACKEND` | No       | `REDIS_URL`              | Result backend for local Celery tasks               |
| `GPU_CELERY_BROKER_URL`       | No       | `amqp://localhost:5674`  | RabbitMQ URL for the GPU Celery worker              |
| `GPU_CELERY_RESULT_BACKEND`   | No       | `redis://localhost:6374` | Result backend for GPU Celery tasks                 |

---

## Google Cloud / Firebase

A Google Cloud service account (`serviceAccountKey.json` or `GOOGLE_APPLICATION_CREDENTIALS_JSON`) is used by multiple
parts of the system: Firebase auth, GCS file storage, Google TTS, Google Speech-to-Text, Google Translate, and Gemini
models. By default we use the local filesystem for file storage and django db for authentication.

| Variable                                                         | Required | Default | Description                                                                                                                                        |
| ---------------------------------------------------------------- | -------- | ------- |----------------------------------------------------------------------------------------------------------------------------------------------------|
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` / `serviceAccountKey.json` | No       | —       | Service account key as a JSON string (alternative to `serviceAccountKey.json`). Required if you want to use any Google Cloud services.             |
| `ENABLE_FIREBASE_AUTH`                                           | No       | `False` | Enable Firebase Authentication instead of local password hash |
| `GOOGLE_CLIENT_ID`                                               | No       | -       | Google OAuth client ID (for Firebase Google sign-in)                                                                                               |
| `FIREBASE_CONFIG`                                                | No       | -       | Firebase web app config JSON string                                                                                                                |
| `GCP_PROJECT`                                                    | No       | -       | Google Cloud project ID                                                                                                                            |
| `GCP_REGION`                                                     | No       | -       | Google Cloud region                                                                                                                                |
| `GS_BUCKET_NAME`                                                 | No       | -       | Use this GCS bucket for file storage instead of local filesystem                                                                                   |
| `GS_MEDIA_PATH`                                                  | No       | -       | Path prefix inside the GCS bucket for media files                                                                                                  |
| `GS_STATIC_PATH`                                                  | No       | -       | Path prefix inside the GCS bucket for static pages                                                                                                 |

### ☁️ Create a google cloud / firebase account

1. Create a [google cloud](https://console.cloud.google.com/) project
2. Create a [firebase project](https://console.firebase.google.com/) (using the same google cloud project)
3. Enable the following services:
   - [Authentication](https://console.firebase.google.com/project/_/authentication)
   - [Storage](https://console.firebase.google.com/project/_/storage)
   - [Speech-to-Text](https://console.cloud.google.com/marketplace/product/google/speech.googleapis.com)
   - [Text-to-Speech](https://console.cloud.google.com/marketplace/product/google/texttospeech.googleapis.com)
   - [Translation API](https://console.cloud.google.com/marketplace/product/google/translate.googleapis.com)
   - [Google Drive API](https://console.cloud.google.com/apis/library/drive.googleapis.com)
4. Go to IAM, Create a service account with following roles:
   - Cloud Datastore User
   - Cloud Speech Administrator
   - Cloud Translation API Admin
   - Firebase Authentication Admin
   - Storage Admin
5. Create and Download a JSON Key for this service account and save it to the project root as `serviceAccountKey.json`.
6. Add your project & bucket name to `.env` (see [configuration.md](configuration.md) for all available settings)

---

## Local filesystem storage

Used by default when `GS_BUCKET_NAME` is unset. Uploaded files are written under
`MEDIA_ROOT` and served by the API server at `MEDIA_URL`.

| Variable     | Required | Default   | Description                                      |
| ------------ | -------- | --------- | ------------------------------------------------ |
| `MEDIA_ROOT` | No       | `./media` | Local directory where uploaded files are stored  |
| `MEDIA_URL`  | No       | `/media/` | URL path under which stored files are served     |

---

## AI model API keys

All optional. Enable the models you intend to use.

| Variable                           | Provider                         |
| ---------------------------------- | -------------------------------- |
| `OPENAI_API_KEY`                   | OpenAI (GPT, Whisper, DALL-E, …) |
| `ANTHROPIC_API_KEY`                | Anthropic (Claude)               |
| `REPLICATE_API_TOKEN`              | Replicate                        |
| `REPLICATE_API_KEY`                | Replicate (alternate key)        |
| `FAL_API_KEY`                      | fal.ai                           |
| `GROQ_API_KEY`                     | Groq                             |
| `FIREWORKS_API_KEY`                | Fireworks AI                     |
| `MISTRAL_API_KEY`                  | Mistral AI                       |
| `HF_TOKEN`                         | Hugging Face                     |
| `SARVAM_API_KEY`                   | Sarvam AI                        |
| `DEEPGRAM_API_KEY`                 | Deepgram (speech-to-text)        |
| `ELEVEN_LABS_API_KEY`              | ElevenLabs (TTS)                 |
| `UBERDUCK_KEY` / `UBERDUCK_SECRET` | Uberduck (TTS)                   |
| `PUBLICAI_API_KEY`                 | PublicAI                         |
| `SEA_LION_API_KEY`                 | SEA-LION                         |
| `GHANA_NLP_SUBKEY`                 | GhanaNLP                         |
| `LELAPA_API_KEY`                   | Lelapa AI                        |
| `INTRON_API_KEY`                   | Intron                           |

---

## Azure AI services

All optional. Needed only for workflows using Azure-hosted models or moderation.

| Variable                          | Description                       |
| --------------------------------- | --------------------------------- |
| `AZURE_SPEECH_REGION`             | Azure Speech region               |
| `AZURE_SPEECH_KEY`                | Azure Speech API key              |
| `AZURE_OPENAI_ENDPOINT_CA`        | Azure OpenAI endpoint (Canada)    |
| `AZURE_OPENAI_KEY_CA`             | Azure OpenAI key (Canada)         |
| `AZURE_OPENAI_ENDPOINT_EASTUS2`   | Azure OpenAI endpoint (East US 2) |
| `AZURE_OPENAI_KEY_EASTUS2`        | Azure OpenAI key (East US 2)      |
| `AZURE_FORM_RECOGNIZER_ENDPOINT`  | Azure Form Recognizer endpoint    |
| `AZURE_FORM_RECOGNIZER_KEY`       | Azure Form Recognizer key         |
| `AZURE_IMAGE_MODERATION_ENDPOINT` | Azure Content Moderator endpoint  |
| `AZURE_IMAGE_MODERATION_KEY`      | Azure Content Moderator key       |
| `AZURE_KEY_VAULT_ENDPOINT`        | Azure Key Vault endpoint          |

---

## Payments

| Variable                 | Description                    |
| ------------------------ | ------------------------------ |
| `STRIPE_SECRET_KEY`      | Stripe secret key              |
| `STRIPE_ENDPOINT_SECRET` | Stripe webhook endpoint secret |
| `PAYPAL_CLIENT_ID`       | PayPal client ID               |
| `PAYPAL_SECRET`          | PayPal secret                  |
| `PAYPAL_BASE`            | PayPal API base URL            |
| `PAYPAL_WEBHOOK_ID`      | PayPal webhook ID              |

---

## Messaging integrations

| Variable                   | Description                                                   |
| -------------------------- | ------------------------------------------------------------- |
| `FB_APP_ID`                | Facebook / Meta app ID                                        |
| `FB_APP_SECRET`            | Facebook / Meta app secret                                    |
| `FB_WEBHOOK_TOKEN`         | Facebook webhook verification token                           |
| `FB_WHATSAPP_CONFIG_ID`    | WhatsApp configuration ID                                     |
| `WHATSAPP_ACCESS_TOKEN`    | WhatsApp access token                                         |
| `SLACK_CLIENT_ID`          | Slack app client ID                                           |
| `SLACK_CLIENT_SECRET`      | Slack app client secret                                       |
| `SLACK_VERIFICATION_TOKEN` | Slack verification token                                      |
| `TELEGRAM_WEBHOOK_SECRET`  | Telegram webhook secret                                       |
| `ONEDRIVE_CLIENT_ID`       | Microsoft OneDrive client ID                                  |
| `ONEDRIVE_CLIENT_SECRET`   | Microsoft OneDrive client secret                              |
| `TWILIO_ACCOUNT_SID`       | Twilio account SID                                            |
| `TWILIO_API_KEY_SID`       | Twilio API key SID                                            |
| `TWILIO_API_KEY_SECRET`    | Twilio API key secret                                         |
| `WS_STREAM_API_BASE_URL`   | derived from `API_BASE_URL`, userd for twilio voice streaming |
| `WS_PROXY_API_BASE_URL`    | derived from `API_BASE_URL`, userd for twilio voice streaming |
| `TWITTER_BEARER_TOKEN`     | Twitter/X bearer token                                        |

---

## Email

| Variable             | Default | Description                                   |
| -------------------- | ------- | --------------------------------------------- |
| `POSTMARK_API_TOKEN` | -       | Postmark API token for transactional email    |
| `ADMIN_EMAILS`       | -       | Comma-separated list of admin email addresses |

---

## Search & maps

| Variable                   | Description                    |
| -------------------------- | ------------------------------ |
| `SERPER_API_KEY`           | Serper Google Search API key   |
| `GOOGLE_GEOCODING_API_KEY` | Google Geocoding API key       |
| `GOOGLE_MAPS_API_KEY`      | Google Maps JavaScript API key |

---

## Vector search (Vespa)

| Variable                  | Default                  | Description                  |
| ------------------------- | ------------------------ | ---------------------------- |
| `VESPA_URL`               | `http://localhost:8085`  | Vespa query/document API URL |
| `VESPA_CONFIG_SERVER_URL` | `http://localhost:19071` | Vespa config server URL      |

---

## Functions runtime (Cloudflare Workers)

See [README.md § Functions runtime](README.md#%EF%B8%8F-functions-runtime-cloudflare-workers) for deployment instructions.

| Variable                  | Description                                                                             |
| ------------------------- | --------------------------------------------------------------------------------------- |
| `CF_FUNCTIONS_URL`        | URL of the Cloudflare Worker executor                                                    |
| `CF_ACCESS_CLIENT_ID`     | Cloudflare Access service token ID, sent as the `CF-Access-Client-Id` header             |
| `CF_ACCESS_CLIENT_SECRET` | Cloudflare Access service token secret, sent as the `CF-Access-Client-Secret` header     |

---

## Modal (serverless GPU)

| Variable             | Description                   |
| -------------------- | ----------------------------- |
| `MODAL_TOKEN_ID`     | Modal token ID                |
| `MODAL_TOKEN_SECRET` | Modal token secret            |
| `MODAL_VLLM_API_KEY` | API key for Modal-hosted vLLM |

---

## LiveKit

| Variable                     | Description        |
| ---------------------------- | ------------------ |
| `LIVEKIT_API_KEY`            | LiveKit API key    |
| `LIVEKIT_API_SECRET`         | LiveKit API secret |
| `LIVEKIT_URL`                | LiveKit server URL |
| `LIVEKIT_SIP_URL`            | LiveKit SIP URL    |
| `LIVEKIT_SIP_TRUNK_NAME`     | SIP trunk name     |
| `LIVEKIT_SIP_TRUNK_USERNAME` | SIP trunk username |
| `LIVEKIT_SIP_TRUNK_PASSWORD` | SIP trunk password |

---

## Scraping proxy

| Variable                  | Description                                |
| ------------------------- | ------------------------------------------ |
| `SCRAPING_PROXY_HOST`     | Proxy host for web scraping                |
| `SCRAPING_PROXY_USERNAME` | Proxy username                             |
| `SCRAPING_PROXY_PASSWORD` | Proxy password                             |
| `SCRAPING_PROXY_CERT_URL` | URL to download the proxy's CA certificate |

---

## Observability

| Variable              | Required      | Description                              |
| --------------------- | ------------- | ---------------------------------------- |
| `SENTRY_DSN`          | **Prod only** | Sentry DSN. Required when `DEBUG=False`. |
| `APOLLO_API_KEY`      | No            | Apollo.io API key                        |
| `LANGFUSE_PUBLIC_KEY` | No            | Langfuse public key                      |
| `LANGFUSE_SECRET_KEY` | No            | Langfuse secret key                      |
| `LANGFUSE_BASE_URL`   | No            | Langfuse base URL (for self-hosted)      |

---

## Misc

| Variable           | Default | Description      |
| ------------------ | ------- | ---------------- |
| `COMPOSIO_API_KEY` | -       | Composio API key |

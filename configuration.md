# Configuration Reference

All settings are read from environment variables (or a `.env` file). Copy `.env.example` to `.env` to get started.

Almost every setting has a sensible default and is optional for local development. The only exceptions are `SECRET_KEY` and `SENTRY_DSN` (both required in production) and the PostgreSQL variables (required if you want PostgreSQL; the server falls back to SQLite without them).

---

## Server URLs

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `APP_BASE_URL` | No | `/` | Public base URL of the frontend (e.g. `https://gooey.ai`) |
| `API_BASE_URL` | No | `/` | Public base URL of the API server |
| `ADMIN_BASE_URL` | No | `https://admin.gooey.ai/` | Public base URL of the Django admin site |
| `WS_STREAM_API_BASE_URL` | No | derived from `API_BASE_URL` | WebSocket URL for streaming API |
| `WS_PROXY_API_BASE_URL` | No | derived from `API_BASE_URL` | WebSocket URL for proxy API |

---

## Django

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DEBUG` | No | `True` | Enable Django debug mode. Set to `False` in production. |
| `SECRET_KEY` | **Prod only** | `"xxxx"` (dev) | Django secret key. Must be a strong random value when `DEBUG=False`. |
| `SENTRY_DSN` | **Prod only** | — | Sentry error reporting DSN. Required when `DEBUG=False`. |
| `SECURE_HSTS_SECONDS` | No | `0` | HSTS max-age in seconds. Set to a non-zero value in production. |
| `SESSION_COOKIE_SECURE` | No | `not DEBUG` | Require HTTPS for session cookies. |

---

## Database (PostgreSQL)

If none of these are set, the server falls back to SQLite (suitable for development only).

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `PGHOST` | For PostgreSQL | — | Postgres host |
| `PGPORT` | For PostgreSQL | — | Postgres port |
| `PGUSER` | For PostgreSQL | — | Postgres user |
| `PGDATABASE` | For PostgreSQL | — | Postgres database name |
| `PGPASSWORD` | For PostgreSQL | — | Postgres password |

---

## Redis / Celery

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `REDIS_URL` | No | `redis://localhost:6379` | Redis URL used for session/cache and Celery results |
| `REDIS_CACHE_URL` | No | `redis://localhost:6379` | Redis URL used as Django cache backend |
| `LOCAL_CELERY_BROKER_URL` | No | `amqp://` | RabbitMQ URL for the local Celery worker |
| `LOCAL_CELERY_RESULT_BACKEND` | No | `REDIS_URL` | Result backend for local Celery tasks |
| `GPU_CELERY_BROKER_URL` | No | `amqp://localhost:5674` | RabbitMQ URL for the GPU Celery worker |
| `GPU_CELERY_RESULT_BACKEND` | No | `redis://localhost:6374` | Result backend for GPU Celery tasks |

---

## Google Cloud / Firebase

A Google Cloud service account (`serviceAccountKey.json` or `GOOGLE_APPLICATION_CREDENTIALS_JSON`) is used by multiple parts of the system: Firebase auth, GCS file storage, Google TTS, Google Speech-to-Text, Google Translate, and Gemini models. Set `SOVEREIGN_DEPLOY=False` to disable Firebase auth and GCS storage (the server will use local auth and filesystem storage instead), but note that Google TTS, STT, Translate, and Gemini will still require valid credentials. See [README](README.md#-alternatively-run-without-firebase-local-auth--filesystem-storage) for details on the local auth/storage mode.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SOVEREIGN_DEPLOY` | No | `True` | Enable Firebase auth and GCS storage |
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | No | — | Service account key as a JSON string (alternative to `serviceAccountKey.json`). Required for Google TTS, STT, Translate, Gemini, and (when `SOVEREIGN_DEPLOY=True`) Firebase auth and GCS storage. |
| `GCP_PROJECT` | No | `dara-c1b52` | Google Cloud project ID |
| `GCP_REGION` | No | `us-central1` | Google Cloud region |
| `GOOGLE_CLIENT_ID` | No | `""` | Google OAuth client ID (for Firebase Google sign-in) |
| `FIREBASE_CONFIG` | No | `""` | Firebase web app config JSON string |
| `GS_BUCKET_NAME` | No | `{GCP_PROJECT}.appspot.com` | GCS bucket for file storage (only used when `SOVEREIGN_DEPLOY=True`) |
| `GS_MEDIA_PATH` | No | `daras_ai/media` | Path prefix inside the GCS bucket |

---

## Local auth + filesystem storage

Only used when `SOVEREIGN_DEPLOY=False`.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MEDIA_ROOT` | No | `./media` | Local directory where uploaded files are stored |
| `MEDIA_URL` | No | `/media/` | URL path under which stored files are served |

---

## AI model API keys

All optional. Enable the models you intend to use.

| Variable | Default | Provider |
|----------|---------|----------|
| `OPENAI_API_KEY` | `""` | OpenAI (GPT, Whisper, DALL-E, …) |
| `ANTHROPIC_API_KEY` | `""` | Anthropic (Claude) |
| `REPLICATE_API_TOKEN` | `""` | Replicate |
| `REPLICATE_API_KEY` | `""` | Replicate (alternate key) |
| `FAL_API_KEY` | `""` | fal.ai |
| `GROQ_API_KEY` | `""` | Groq |
| `FIREWORKS_API_KEY` | `""` | Fireworks AI |
| `MISTRAL_API_KEY` | `""` | Mistral AI |
| `HF_TOKEN` | `""` | Hugging Face |
| `SARVAM_API_KEY` | `""` | Sarvam AI |
| `DEEPGRAM_API_KEY` | `""` | Deepgram (speech-to-text) |
| `ELEVEN_LABS_API_KEY` | `""` | ElevenLabs (TTS) |
| `UBERDUCK_KEY` / `UBERDUCK_SECRET` | `None` | Uberduck (TTS) |
| `PUBLICAI_API_KEY` | `""` | PublicAI |
| `SEA_LION_API_KEY` | `""` | SEA-LION |
| `GHANA_NLP_SUBKEY` | `""` | GhanaNLP |
| `LELAPA_API_KEY` | `""` | Lelapa AI |
| `INTRON_API_KEY` | `""` | Intron |

---

## Azure AI services

All optional. Needed only for workflows using Azure-hosted models or moderation.

| Variable | Default | Description |
|----------|---------|-------------|
| `AZURE_SPEECH_REGION` | `""` | Azure Speech region |
| `AZURE_SPEECH_KEY` | `""` | Azure Speech API key |
| `AZURE_OPENAI_ENDPOINT_CA` | `""` | Azure OpenAI endpoint (Canada) |
| `AZURE_OPENAI_KEY_CA` | `""` | Azure OpenAI key (Canada) |
| `AZURE_OPENAI_ENDPOINT_EASTUS2` | `""` | Azure OpenAI endpoint (East US 2) |
| `AZURE_OPENAI_KEY_EASTUS2` | `""` | Azure OpenAI key (East US 2) |
| `AZURE_FORM_RECOGNIZER_ENDPOINT` | `""` | Azure Form Recognizer endpoint |
| `AZURE_FORM_RECOGNIZER_KEY` | `""` | Azure Form Recognizer key |
| `AZURE_IMAGE_MODERATION_ENDPOINT` | `""` | Azure Content Moderator endpoint |
| `AZURE_IMAGE_MODERATION_KEY` | `""` | Azure Content Moderator key |
| `AZURE_KEY_VAULT_ENDPOINT` | `""` | Azure Key Vault endpoint |

---

## Payments

| Variable | Default | Description |
|----------|---------|-------------|
| `STRIPE_SECRET_KEY` | `None` | Stripe secret key |
| `STRIPE_ENDPOINT_SECRET` | `None` | Stripe webhook endpoint secret |
| `PAYPAL_CLIENT_ID` | `""` | PayPal client ID |
| `PAYPAL_SECRET` | `""` | PayPal secret |
| `PAYPAL_BASE` | `""` | PayPal API base URL |
| `PAYPAL_WEBHOOK_ID` | `""` | PayPal webhook ID |

---

## Messaging integrations

| Variable | Default | Description |
|----------|---------|-------------|
| `FB_APP_ID` | `""` | Facebook / Meta app ID |
| `FB_APP_SECRET` | `""` | Facebook / Meta app secret |
| `FB_WEBHOOK_TOKEN` | `""` | Facebook webhook verification token |
| `FB_WHATSAPP_CONFIG_ID` | `""` | WhatsApp configuration ID |
| `WHATSAPP_ACCESS_TOKEN` | `None` | WhatsApp access token |
| `SLACK_CLIENT_ID` | `""` | Slack app client ID |
| `SLACK_CLIENT_SECRET` | `""` | Slack app client secret |
| `SLACK_VERIFICATION_TOKEN` | `""` | Slack verification token |
| `TELEGRAM_WEBHOOK_SECRET` | `""` | Telegram webhook secret |
| `ONEDRIVE_CLIENT_ID` | `""` | Microsoft OneDrive client ID |
| `ONEDRIVE_CLIENT_SECRET` | `""` | Microsoft OneDrive client secret |
| `TWILIO_ACCOUNT_SID` | `""` | Twilio account SID |
| `TWILIO_API_KEY_SID` | `""` | Twilio API key SID |
| `TWILIO_API_KEY_SECRET` | `""` | Twilio API key secret |
| `TALK_JS_APP_ID` | `""` | TalkJS app ID |
| `TALK_JS_SECRET_KEY` | `""` | TalkJS secret key |
| `TWITTER_BEARER_TOKEN` | `None` | Twitter/X bearer token |

---

## Email

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTMARK_API_TOKEN` | `None` | Postmark API token for transactional email |
| `ADMIN_EMAILS` | `""` | Comma-separated list of admin email addresses |

---

## Search & maps

| Variable | Default | Description |
|----------|---------|-------------|
| `SERPER_API_KEY` | `None` | Serper Google Search API key |
| `GOOGLE_GEOCODING_API_KEY` | `""` | Google Geocoding API key |
| `GOOGLE_MAPS_API_KEY` | `""` | Google Maps JavaScript API key |

---

## Vector search (Vespa)

| Variable | Default | Description |
|----------|---------|-------------|
| `VESPA_URL` | `http://localhost:8085` | Vespa query/document API URL |
| `VESPA_CONFIG_SERVER_URL` | `http://localhost:19071` | Vespa config server URL |

---

## Functions runtime

The Functions recipe executes user-supplied JavaScript in a sandboxed Deno HTTP server (`functions/executor.js`). By default Gooey.AI runs this on [Deno Deploy](https://deno.com/deploy), but you can self-host it with Docker:

```bash
docker run --rm \
  -e GOOEY_AUTH_TOKEN=your-secret \
  -p 8000:8000 \
  -v "$(pwd)/functions/executor.js:/executor.js" \
  denoland/deno:latest \
  run --allow-env --allow-net /executor.js
```

Then point Gooey Server at it in `.env`:

```env
DENO_FUNCTIONS_URL=http://localhost:8000
DENO_FUNCTIONS_AUTH_TOKEN=your-secret
```

| Variable | Default | Description |
|----------|---------|-------------|
| `DENO_FUNCTIONS_URL` | `""` | URL of the Deno executor service |
| `DENO_FUNCTIONS_AUTH_TOKEN` | `""` | Auth token sent as `Authorization: Basic <token>` |

---

## Modal (serverless GPU)

| Variable | Default | Description |
|----------|---------|-------------|
| `MODAL_TOKEN_ID` | `""` | Modal token ID |
| `MODAL_TOKEN_SECRET` | `""` | Modal token secret |
| `MODAL_VLLM_API_KEY` | `""` | API key for Modal-hosted vLLM |

---

## LiveKit

| Variable | Default | Description |
|----------|---------|-------------|
| `LIVEKIT_API_KEY` | `""` | LiveKit API key |
| `LIVEKIT_API_SECRET` | `""` | LiveKit API secret |
| `LIVEKIT_URL` | `""` | LiveKit server URL |
| `LIVEKIT_SIP_URL` | `""` | LiveKit SIP URL |
| `LIVEKIT_SIP_TRUNK_NAME` | `""` | SIP trunk name |
| `LIVEKIT_SIP_TRUNK_USERNAME` | `""` | SIP trunk username |
| `LIVEKIT_SIP_TRUNK_PASSWORD` | `""` | SIP trunk password |

---

## Scraping proxy

| Variable | Default | Description |
|----------|---------|-------------|
| `SCRAPING_PROXY_HOST` | `""` | Proxy host for web scraping |
| `SCRAPING_PROXY_USERNAME` | `""` | Proxy username |
| `SCRAPING_PROXY_PASSWORD` | `""` | Proxy password |
| `SCRAPING_PROXY_CERT_URL` | `""` | URL to download the proxy's CA certificate |

---

## Observability

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SENTRY_DSN` | **Prod only** | — | Sentry DSN. Required when `DEBUG=False`. |
| `APOLLO_API_KEY` | No | `None` | Apollo.io API key |
| `LANGFUSE_PUBLIC_KEY` | No | `None` | Langfuse public key |
| `LANGFUSE_SECRET_KEY` | No | `None` | Langfuse secret key |
| `LANGFUSE_BASE_URL` | No | `None` | Langfuse base URL (for self-hosted) |

---

## Misc

| Variable | Default | Description |
|----------|---------|-------------|
| `GPU_SERVER_1` | `http://gpu-1.gooey.ai` | URL of the GPU inference server |
| `COMPOSIO_API_KEY` | `""` | Composio API key |

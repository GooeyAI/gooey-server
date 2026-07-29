# Platform Independence

This document describes how Gooey Server complies with [Indicator 4 (Platform Independence)](https://github.com/DPGAlliance/dpg-resources/wiki/4.-Platform-Independence) of the DPG Standard, following the [DPG Alliance Platform Independence guide](https://github.com/DPGAlliance/dpg-resources/tree/main/docs/platform-independence).

For every proprietary or closed-source component, we list the open alternative, the mechanism used to swap it (abstraction layer, feature flag, or migration path), and where the relevant code lives.

Gooey Server itself is licensed under [Apache License 2.0](LICENSE).

---

## Summary

| Dependency | Type | Open alternative | Swap mechanism | Status |
|---|---|---|---|---|
| PostgreSQL | Database | — (already open, PostgreSQL License) | n/a | ✅ Open |
| RabbitMQ | Message broker | — (already open, MPL-2.0) | n/a | ✅ Open |
| Vespa | Search / vector store | — (already open, Apache-2.0) | n/a | ✅ Open |
| Redis | Cache / result backend | Redis 8 under AGPL-3.0 (OSI-approved); Valkey (BSD-3) also drop-in | Container image only — zero code coupling | ✅ Open (pinned `redis:8`) |
| Firebase Auth | Authentication | Built-in local Django auth | Feature flag (`ENABLE_FIREBASE_AUTH`, default **off**) | ✅ Abstracted |
| Google Cloud Storage | File storage | Local filesystem storage | Feature flag (`GS_BUCKET_NAME`, default **unset**) | ✅ Abstracted |
| Cloud LLM APIs (OpenAI, Anthropic, Google, etc.) | AI models | Any OpenAI-compatible server (Ollama, vLLM, LocalAI, llama.cpp) | Abstraction layer (`AIModelSpec.base_url`) | ✅ Abstracted |
| Cloud STT / TTS / embeddings | AI models | Self-hosted Whisper, Seamless, MMS, Bark, E5/GTE on GPU worker | Abstraction layer (provider enums + GPU Celery worker) | ✅ Abstracted |
| Stripe / PayPal | Payments | Not required — billing gracefully disabled when keys unset (default) | Feature flag with graceful UI fallback | ✅ Abstracted |
| Azure Content Moderator | Image safety checker | Open-weight NSFW classifier on GPU worker | Abstraction layer + env toggle | 🔧 In progress |
| Azure Key Vault | Managed secrets | Encrypted-at-rest storage in PostgreSQL | Pluggable secrets backend | 🔧 In progress |
| Modal (MMS TTS, Omnilingual ASR) | AI model hosting | Optional feature; core TTS/ASR works via GPU worker or other providers | Optional integration | ✅ Optional |
| Font Awesome Pro | UI icons | Font Awesome Free (self-hosted) | Asset swap for self-hosted builds | 🔧 In progress |
| Google Tag Manager | Analytics | Not required for operation | Env-gated script (unset ⇒ not rendered) | 🔧 In progress |
| WhatsApp / Slack / Facebook / Twilio integrations | Messaging connectors | Optional integrations; core product functions without them | Optional (keys unset ⇒ disabled) | ✅ Optional |

> Deployment, testing, CI/CD, containerization, and monitoring tools (Docker, GitHub Actions, Sentry) are exempt from platform independence per the DPG guide.

---

## 1. Core infrastructure — fully open

The mandatory backing services are all under OSI-approved licenses and ship in [docker-compose.local.yml](docker-compose.local.yml):

- **PostgreSQL 15** (PostgreSQL License) — primary database for all application data, via the Django ORM.
- **RabbitMQ** (MPL-2.0) — Celery task broker.
- **Vespa** (Apache-2.0) — search and vector store for document retrieval, self-hosted.
- **Redis 8** (AGPL-3.0, OSI-approved) — cache and Celery result backend, pinned in [docker-compose.local.yml](docker-compose.local.yml). The application has zero Redis-version coupling: it uses only connection URLs ([daras_ai_v2/settings.py#L455](daras_ai_v2/settings.py#L455)) and the MIT-licensed `redis-py` client over the standard wire protocol, so [Valkey](https://valkey.io) (BSD-3-Clause) is an equally drop-in alternative with no code changes.

## 2. Authentication — abstraction layer (Path 2)

Firebase Auth is **optional and off by default**. The toggle is `ENABLE_FIREBASE_AUTH` ([daras_ai_v2/settings.py#L255](daras_ai_v2/settings.py#L255), default `False`).

- Router selection: [server.py#L104-L111](server.py#L104) mounts either `routers/firebase_auth.py` or `routers/local_auth.py` based on the flag.
- Session verification: [auth/auth_backend.py#L38-L41](auth/auth_backend.py#L38) selects the matching `authenticate_session` implementation behind a common interface.
- The open path, [routers/local_auth.py](routers/local_auth.py), is a complete email/password flow built on Django's auth primitives (password hashing, session invalidation on password change, admin-driven password reset). It is the default for self-hosted deployments — no Google account or Firebase project needed.

Users previously created via Firebase are interoperable: accounts migrated from Firebase set a local password on first login ([routers/local_auth.py#L139-L156](routers/local_auth.py#L139)).

## 3. File storage — abstraction layer (Path 2)

Google Cloud Storage is **optional and off by default**. When `GS_BUCKET_NAME` is unset (the default), all uploads are stored on the local filesystem under `MEDIA_ROOT` and served by the app itself.

- Branch points: [daras_ai/image_input.py#L71-L137](daras_ai/image_input.py#L71) (`upload_file_from_bytes` and friends fall through to `save_local_file_from_bytes`).
- Guard: settings assert GCS is only enabled when credentials are actually provided ([daras_ai_v2/settings.py#L279](daras_ai_v2/settings.py#L279)).

Any S3-compatible open object store (e.g., MinIO, AGPL-3.0) can also be fronted via the local path or a reverse proxy without code changes to callers, since all call sites go through the same upload helpers.

## 4. AI models — abstraction layers with self-hosted alternatives (Path 2)

Gooey Server is multi-provider by design. No single AI vendor is mandatory. Full setup instructions for every self-hosted path are in [docs/local-models.md](docs/local-models.md).

### LLMs
Any server exposing an OpenAI-compatible `/v1/chat/completions` endpoint works — **Ollama, vLLM, LocalAI, LM Studio, llama.cpp** — by setting `base_url`/`api_key`/`model_id` on an `AIModelSpec` in the Django admin ([daras_ai_v2/language_model.py](daras_ai_v2/language_model.py)). No code changes required; this is runtime configuration.

### Embeddings
Open-weight models (`intfloat/e5-*`, `thenlper/gte-*`) run on the self-hosted GPU Celery worker ([daras_ai_v2/embedding_model.py](daras_ai_v2/embedding_model.py)). Cloud embedding APIs are optional alternatives, not requirements.

### Speech-to-text
Self-hosted **Whisper**, **Seamless M4T**, and **MMS** run on the GPU worker ([daras_ai_v2/asr.py](daras_ai_v2/asr.py)). Cloud STT providers (Google, Deepgram, Azure, ElevenLabs) are optional alternatives behind the same `AsrModels` enum.

### Text-to-speech
Self-hosted **Bark** runs on the GPU worker; cloud TTS providers are optional alternatives behind the `TextToSpeechProviders` enum ([daras_ai_v2/text_to_speech_settings_widgets.py](daras_ai_v2/text_to_speech_settings_widgets.py)).

### Modal-hosted models
Two models (MMS TTS, Omnilingual ASR) are deployed on [Modal](https://modal.com). These are **optional features**: TTS and ASR each have multiple self-hosted and provider alternatives, and the platform functions fully without Modal credentials.

## 5. Payments — feature flag with graceful degradation (Path 2)

Stripe and PayPal power billing on the hosted gooey.ai service. Payment processing is **not required to run the software**, and billing degrades gracefully when disabled:

- Payment credentials default to unset: `STRIPE_SECRET_KEY = config("STRIPE_SECRET_KEY", None)` ([daras_ai_v2/settings.py#L415](daras_ai_v2/settings.py#L415)), so a fresh self-hosted install has payments off with no configuration needed.
- The billing page checks the flag and falls back cleanly: when `STRIPE_SECRET_KEY` is unset, [daras_ai_v2/billing.py#L247](daras_ai_v2/billing.py#L247) hides all plans, checkout, and payment-method UI and instead directs operators to top up credits via the Django admin. No payment provider is ever contacted.
- Background billing tasks (e.g., auto-recharge) only run for workspaces with a paid subscription, which cannot exist when payments are disabled — so no code path reaches Stripe/PayPal on a self-hosted deployment.

Credit accounting itself is fully open (rows in PostgreSQL); self-hosted operators grant credits through the Django admin.

## 6. Image safety checker — abstraction layer (Path 2, in progress)

Image moderation currently calls Azure Content Moderator ([daras_ai_v2/azure_image_moderation.py](daras_ai_v2/azure_image_moderation.py)) from [daras_ai_v2/safety_checker.py](daras_ai_v2/safety_checker.py). Text moderation already runs through the LLM abstraction (any configured model, including self-hosted ones).

Mechanism (in progress): a provider interface for image moderation with an open-weight NSFW classifier running on the self-hosted GPU Celery worker (the same infrastructure that serves Whisper and embeddings), selected by an environment toggle. Azure becomes one optional provider among alternatives.

## 7. Managed secrets — pluggable backend (Path 2, in progress)

The managed-secrets feature (user-supplied API keys) currently stores values in Azure Key Vault ([managed_secrets/models.py](managed_secrets/models.py)).

Mechanism (in progress): a pluggable secrets backend with encrypted-at-rest storage in PostgreSQL as the default for self-hosted deployments; Azure Key Vault becomes an opt-in backend. [OpenBao](https://openbao.org) (MPL-2.0) is a further open external-vault option.

## 8. Frontend assets (in progress)

- **Font Awesome Pro** is loaded from a kit URL. Self-hosted builds will ship with Font Awesome Free (or an equivalent open icon set) bundled locally.
- **Google Tag Manager** will render only when a GTM ID is configured; unset (the default for self-hosted) means no analytics script is served.
- Static brand assets currently referenced from cloud storage URLs will be bundled with the repository.

## 9. Optional messaging integrations

WhatsApp, Slack, Facebook Messenger, and Twilio voice/SMS connectors let bots built on Gooey reach users on those networks. They are inherently integrations *to* proprietary platforms, are disabled unless the corresponding credentials are set, and are not required for any core functionality (the web widget, API, and web UI are fully independent of them).

---

## Verifying a fully-open deployment

The reference self-hosted stack runs with **zero proprietary services**:

```bash
docker compose -f docker-compose.local.yml up -d
```

- Auth: local Django email/password (`ENABLE_FIREBASE_AUTH` unset)
- Storage: local filesystem (`GS_BUCKET_NAME` unset)
- LLM: Ollama or any OpenAI-compatible server (see [docs/local-models.md](docs/local-models.md))
- STT/TTS/embeddings: GPU Celery worker (optional, for AI features that need it)
- Payments, analytics, cloud moderation, Key Vault: disabled (keys unset)

Backing services: PostgreSQL, RabbitMQ, Redis 8 (AGPL-3.0), Vespa — all open source.

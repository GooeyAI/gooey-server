# Gooey ComfyUI Cloud (comfy.gooey.ai)

A separate service that gives every Gooey user a cloud-hosted [ComfyUI](https://github.com/comfyanonymous/ComfyUI),
logged in with their **Gooey account**, billed in **Gooey credits** to their
**selected workspace**, with a **Gooey header** on top of the ComfyUI app for
navigation, workspace switching, and live credit balance.

```
                      browser (comfy.gooey.ai)
                               │
                               ▼
   ┌───────────────────────────────────────────────────────┐
   │  ComfyUI Gateway  (this directory — FastAPI)          │
   │  • SSO with gooey.ai (signed short-lived tokens)      │
   │  • signed session cookie (uid + workspaces)           │
   │  • injects the Gooey header into ComfyUI's index.html │
   │  • reverse-proxies HTTP + WebSocket to the backend    │
   │  • bills 1 GPU-minute of credits per minute of use    │
   │  • idle reaper stops instances after inactivity       │
   └──────────┬───────────────────────────┬────────────────┘
              │ server-to-server          │ per-workspace instances
              ▼ (COMFY_SERVICE_TOKEN)     ▼
   ┌─────────────────────┐     ┌───────────────────────────┐
   │ gooey-server        │     │ Modal sandboxes           │
   │ /comfy/sso/         │     │ (comfy_modal.py)          │
   │ /__/comfy/api/*     │     │ ComfyUI + comfy-cli, GPU, │
   │ (verify SSO, list   │     │ persistent Volume per     │
   │  workspaces, deduct │     │ workspace for models/     │
   │  credits)           │     │ outputs/custom nodes      │
   └─────────────────────┘     └───────────────────────────┘
```

## How it works

### Login with the Gooey account

comfy.gooey.ai and gooey.ai are different origins, and the gooey session
cookie is host-only, so the gateway uses a redirect-based SSO handshake
instead of sharing cookies:

1. Unauthenticated navigation to `comfy.gooey.ai/*` redirects to
   `gooey.ai/comfy/sso/?next=<path>` (`routers/comfy_api.py` on gooey-server).
2. That endpoint runs behind gooey-server's normal auth middleware. If the
   user isn't logged in it bounces through `/login/` first (the comfy URL is
   in `SAFE_URLS`, so the post-login redirect is allowed).
3. It then mints a 5-minute token signed with `SECRET_KEY`
   (salt `gooey-comfy-sso`) and redirects to
   `comfy.gooey.ai/auth/callback?token=…`.
4. The gateway exchanges the token server-to-server
   (`POST /__/comfy/api/verify-sso/`, authenticated with the shared
   `COMFY_SERVICE_TOKEN` bearer) and receives the user's profile plus all
   workspaces they're a member of, with balances.
5. The gateway sets its own signed `comfy_session` cookie. Nothing secret
   from gooey.ai ever reaches the browser or the ComfyUI upstream (the proxy
   strips the `Cookie` header).

### Workspaces & billing

- The Gooey header has a **workspace switcher**; the selection is stored in
  the gateway session (mirroring gooey-server's `selected-workspace-id`).
- Each workspace gets its **own ComfyUI instance** and its own Modal Volume
  (`comfyui-workspace-<id>`) — models, custom nodes, inputs and outputs are
  shared by workspace members and persist across sessions.
- While an instance is up, the gateway reports usage every minute to
  `POST /__/comfy/api/usage/`. Pricing stays on gooey-server
  (`COMFY_CREDITS_PER_GPU_MINUTE`, default 10 credits/GPU-minute); deduction
  uses the same idempotent `Workspace.add_balance` primitive as recipe runs,
  with deterministic invoice ids (`<sandbox_id>/<tick>`) so retries can never
  double-charge. Transactions appear in the workspace's normal billing
  history on gooey.ai.
- Launch is refused below `MIN_CREDITS_TO_LAUNCH`; when a workspace runs out
  of credits mid-session the instance is stopped and the user is pointed at
  the gooey.ai billing page.
- The idle reaper stops instances after `IDLE_TIMEOUT_SECONDS` (default
  15 min) without proxy traffic; Modal sandboxes additionally have a hard
  12-hour lifetime cap as a spend backstop.

### The Gooey header

`gateway/header.py` injects a `<style>+<script>` snippet into ComfyUI's
`index.html` as it passes through the proxy. The script inserts a fixed
44 px bar (Gooey logo → gooey.ai, workspace switcher, live credit balance
refreshed every 30 s via `/gooey/api/me`, add-credits link, avatar, logout)
and pushes the ComfyUI app down below it. DOM-insertion via script keeps it
robust against changes to ComfyUI's markup.

### GPU backends

`COMFY_BACKEND` selects the compute backend (`gateway/backends.py`):

- **`modal`** (default): boots a `modal.Sandbox` per workspace from the
  pre-baked image in `comfy_modal.py` (comfy-cli + pinned ComfyUI, NVIDIA
  deps), exposed through a Modal tunnel. GPU type via `MODAL_GPU`
  (default `L4`).
- **`local`**: same per-workspace isolation, but each instance is a local
  `comfy launch` subprocess instead of a Modal sandbox — for local installs
  that want to use their own machine (and GPU, if `nvidia-smi` finds one;
  otherwise ComfyUI runs with `--cpu`). Per-workspace data lives under
  `COMFY_LOCAL_DATA_DIR` (default `~/.gooey-comfy`), ports are allocated
  from `COMFY_LOCAL_PORT_START` (default 8190). Credits are **not**
  deducted unless `COMFY_LOCAL_BILLING=1`, since it's your own hardware.
  Requires comfy-cli: `pip install comfy-cli && comfy --skip-prompt install`.
- **`static`**: one fixed upstream ComfyUI (`STATIC_COMFY_URL`) shared by
  everyone — for pointing at an already-running ComfyUI or a self-managed
  GPU box / RunPod pod. Billed only for *active* minutes since the GPU
  isn't dedicated.

Other managed ComfyUI providers can be added as small `BaseBackend`
subclasses (launch + terminate + url).

## Deployment

### 1. gooey-server side (already wired in this repo)

Set env vars on the main gooey-server deployment:

| var | value |
|---|---|
| `COMFY_BASE_URL` | `https://comfy.gooey.ai` |
| `COMFY_SERVICE_TOKEN` | long random secret, shared with the gateway |
| `COMFY_CREDITS_PER_GPU_MINUTE` | e.g. `10` |

### 2. Bake the Modal image

```bash
cd comfy
pip install -r requirements.txt
modal token set  # or MODAL_TOKEN_ID / MODAL_TOKEN_SECRET
python comfy_modal.py
```

### 3. Deploy the gateway

Any container host works (Cloud Run / Fly / GKE). It's stateless except for
in-memory instance tracking, so run **a single replica** (or add sticky
routing by workspace if scaling out).

```bash
docker build -t gooey-comfy-gateway comfy/
docker run -p 8501:8501 \
  -e COMFY_BASE_URL=https://comfy.gooey.ai \
  -e GOOEY_APP_BASE_URL=https://gooey.ai \
  -e GOOEY_API_BASE_URL=https://api.gooey.ai \
  -e COMFY_SERVICE_TOKEN=... \
  -e SECRET_KEY=... \
  -e MODAL_TOKEN_ID=... -e MODAL_TOKEN_SECRET=... \
  -e MODAL_GPU=L4 \
  gooey-comfy-gateway
```

Point the `comfy.gooey.ai` DNS record at the deployment (TLS required —
the session cookie is `Secure` on https).

### 4. Local development

```bash
# terminal 1: gooey-server as usual (localhost:8080 / :3000)
# terminal 2:
cd comfy
pip install -r requirements.txt comfy-cli
comfy --skip-prompt install   # one-time; picks up your GPU if you have one
COMFY_BACKEND=local \
  SECRET_KEY=dev COMFY_SERVICE_TOKEN=dev \
  GOOEY_APP_BASE_URL=http://localhost:3000 \
  GOOEY_API_BASE_URL=http://localhost:8080 \
  COMFY_BASE_URL=http://localhost:8501 \
  uvicorn gateway.main:app --port 8501 --reload
```

(set `COMFY_SERVICE_TOKEN=dev` on the gooey-server side too.)

`COMFY_BACKEND=local` gives you the full production behavior — per-workspace
instances, launch/idle lifecycle, header — but everything runs on your own
machine and no credits are deducted. If you already have a ComfyUI running,
use `COMFY_BACKEND=static STATIC_COMFY_URL=http://localhost:8188` instead.

## Endpoint reference

Gateway (comfy.gooey.ai):

| route | purpose |
|---|---|
| `GET /login` | kick off SSO via gooey.ai |
| `GET /auth/callback?token=` | finish SSO, set session cookie |
| `GET /gooey/logout` | clear session, back to gooey.ai |
| `GET /gooey/api/me` | fresh profile + workspace balances (header polls this) |
| `POST /gooey/switch-workspace` | change the active workspace |
| `WS /ws` | proxied ComfyUI websocket |
| `* /{path}` | authenticated reverse proxy to the workspace's ComfyUI |

gooey-server (`routers/comfy_api.py`):

| route | auth | purpose |
|---|---|---|
| `GET /comfy/sso/` | browser session | mint SSO token, redirect to gateway |
| `POST /__/comfy/api/verify-sso/` | service token | token → user + workspaces |
| `GET /__/comfy/api/users/{uid}/` | service token | refresh profile/balances |
| `POST /__/comfy/api/usage/` | service token | bill gpu_ms to a workspace (idempotent) |
| `GET /__/comfy/api/workspaces/{id}/balance/` | service token | pre-flight balance check |

<h3 align="center">
  <img src="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/cdc58fe0-2da1-11ef-84df-02420a0001f4/githubbanner.png"
  />
</h3>
<p align="center">
  <a href="https://gooey.ai">🏠 Homepage</a> ·
  <a href="https://gooey.ai/explore">👾 Explore Workflows</a> ·
  <a href="https://gooey.ai/docs">📚 Docs</a> ·
  <a href="https://gooey.ai/api">🤖 API</a> ·
  <a href="https://gooey.ai/discord">🛟 Discord</a> ·
  <a href="https://gooey.ai/account">💃🏾 Start Building</a>
</p>

<div>
  <p align="center">
    <a
    href="https://x.com/GooeyAI">
        <img src="https://img.shields.io/badge/X/Twitter-000000?style=for-the-badge&logo=x&logoColor=white" />
    </a>
    <a href="https://in.linkedin.com/company/gooeyai">
        <img src="https://img.shields.io/badge/LinkedIn-0077B5?style=for-the-badge&logo=linkedin&logoColor=white" />
    </a>
    <a href="https://gooey.ai/discord">
        <img src="https://img.shields.io/badge/Discord-5865F2?style=for-the-badge&logo=discord&logoColor=white" />
    </a>
    <a href="https://www.youtube.com/@gooeyai">
        <img src="https://img.shields.io/badge/YouTube-FF0000?style=for-the-badge&logo=youtube&logoColor=white" />
    </a>
 </p>
</div>

[Gooey.AI](http://gooey.ai/) is the low-code orchestration platform with **discoverable workflows** & **unified billing to all of GenAI universe.**

# 🤖🍲 What is Gooey Server?

Gooey.AI is a low-code AI recipe platform and Gooey Server is our core repo.  
It allows users to discover, customize, and deploy AI "recipes" using the best of private and open-source AI,
all using a single API with a single auth token.  
Recipes are workflows that incorporate various models to accomplish a task; they are designed to be highly customizable and shareable.

## 🧑‍💻 Who is this for and why would I want to use it?

For most developers, we DO NOT recommend running or forking Gooey Server; use our [APIs](https://gooey.ai/api/) or [client SDK](https://github.com/GooeyAI/python-sdk) instead.  
The repo is intended only for developers who want to run and deploy their own server cluster or run Gooey locally for development purposes.

Specifically, this repo may be for you if:

- You want to create a new recipe (instead of changing the parameters on an existing one)
- You want to add an AI model that we currently don’t support.
- You are an enterprise with specific requirements regarding data practices, such as using specific cloud providers.
- You want to add some other functionality that we don’t support.

## 🏗️ Architecture

```
                 +-----------+          +-----------------+
                 |  Browser  |          |   API Clients   |
                 +-----+-----+          |  (SDKs / curl)  |
                       |                +--------+--------+
                 :3000 |                         |
                       v                         |
          +-------------------------+            |
          |        gooey-gui        |            |
          | (Node / Remix frontend) |            | :8080
          +------------+------------+            |
                       |                         |
                       | render requests         |
                       v                         v
+--------------+  +-------------------------------------+
| Django Admin |  |      Python API + GUI Server        |
|    :8000     |  |        (FastAPI, server.py)         |
+------+-------+  +------------------+------------------+
       |                              |
       |                              |  enqueue recipe runs (amqp)
       |                              v
       |          +-------------------------------------+     +-----------------+
       |          |           Celery Workers            |---->| GenAI providers |
       |          |            (celeryapp)              |     | OpenAI, Gemini, |
       |          +------------------+------------------+     | Replicate, ...  |
       |                              |                       +-----------------+
       v                              v
+---------------------------------------------------------------------+
|                           Backing Services                          |
|                                                                     |
|  +-----------+   +-----------+   +------------+   +--------------+  |
|  | Postgres  |   |   Redis   |   |  RabbitMQ  |   |    Vespa     |  |
|  |   :5432   |   |   :6379   |   |   :5672    |   |    :8085     |  |
|  |  app DB   |   |  cache +  |   |   celery   |   |   vector +   |  |
|  |           |   |  pub/sub  |   |   broker   |   | text search  |  |
|  +-----------+   +-----------+   +------------+   +--------------+  |
+---------------------------------------------------------------------+
```

- **gooey-gui** (`gooey-gui/`) — Remix/React frontend. It asks the Python server to render each page as a JSON component tree, renders that in React, and subscribes to Redis pub/sub so pages update live while a recipe runs.
- **Python API + GUI Server** (`server.py`) — FastAPI app that serves the public API and the page-render endpoints used by gooey-gui.
- **Celery Workers** (`celeryapp/`) — run the actual recipes: consume jobs from RabbitMQ, call the GenAI providers, save results to Postgres, and publish progress updates to Redis.
- **Django Admin** (`gooeysite/`) — admin UI over the same Postgres database.
- Services talk directly to Postgres (app data), Redis (cache + realtime pub/sub), and Vespa (vector + full-text search for the doc search / RAG features).

## 📋 Setup

### ⚡ Quickstart

The fastest way to run everything locally is Docker Compose. It starts postgres, redis, rabbitmq, vespa, and the app services (API, Django admin, celery, gooey-gui) in one command.

**1. Clone the Gooey Server Repo**
```bash
git clone https://github.com/GooeyAI/gooey-server.git
```

**2. Install Docker**

- **macOS** — install [OrbStack](https://orbstack.dev/download) (recommended on Apple Silicon; native arm64, fast builds)
> [!NOTE]
> OrbStack requires you to start it the first time.

- **Linux** — install [Docker Engine](https://docs.docker.com/engine/install/) and the [Compose plugin](https://docs.docker.com/compose/install/linux/)
- **Windows** — install [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/)

**3. Start the stack**

```bash
docker compose -f docker-compose.local.yml up --build
```

The first build takes a few minutes. After startup:

| Service | URL (localhost)               |
| ------- | ----------------------------- |
| UI      | http://localhost:3000/explore |
| API     | http://localhost:8080/docs    |
| Admin   | http://localhost:8000         |

**First-time setup** — run once after the stack is up (migrations, local LLM models, default Django admin user):

```bash
docker compose -f docker-compose.local.yml run --rm admin ./manage.py runscript setup_local
```

Then log in to Django admin at http://localhost:8000 with username **`admin`** and password **`admin`**. These credentials are for local development only.

To stop everything:

```bash
docker compose -f docker-compose.local.yml down
```

> **Note:** `Dockerfile.local` is a lightweight image for local development. It skips playwright and mediapipe, so a few recipes that depend on those won't work in-container. For full parity, use the manual setup steps below instead.

### ⚙️ Configuration reference

For a full list of all available settings with defaults and descriptions, see [configuration.md](configuration.md).

### 💻 Setup (Mac)

- Install [pyenv](https://github.com/pyenv/pyenv) & install the same python version as in our [Dockerfile](Dockerfile)
- Install [poetry](https://python-poetry.org/docs/)
- Clone this github repo
- Create & activate a virtualenv (e.g. `poetry shell`)
- Run `poetry install --with dev`
- Install [redis](https://redis.io/docs/getting-started/installation/install-redis-on-mac-os/), [rabbitmq](https://www.rabbitmq.com/install-homebrew.html), and [postgresql](https://formulae.brew.sh/formula/postgresql@15) (e.g. `brew install redis rabbitmq postgresql@15`)
- Enable background services for `redis`, `rabbitmq`, and `postgresql` (e.g. with `brew services start redis` and similar for `rabbitmq` and `postgresql`)
- Use `sqlcreate` helper to create a user and database for gooey:
  - `./manage.py sqlcreate | psql postgres`
  - make sure you are able to access the database with `psql -W -U gooey gooey` (and when prompted for password, entering `gooey`)
- Run `./manage.py migrate`
- Install the zbar library (`brew install zbar`)
- (optional) Install imagemagick - Needed for HEIC image support - https://docs.wand-py.org/en/0.5.7/guide/install.html

```
brew install freetype imagemagick
export MAGICK_HOME=/opt/homebrew
```

### 🐧 Setup (Linux)

- Install [pyenv](https://github.com/pyenv/pyenv) & install the same python version as in our [Dockerfile](Dockerfile) (currently Python 3.10)
  - `curl https://pyenv.run | bash`
- Install [poetry](https://python-poetry.org/docs/)
  - This is likely available in your distro's package repos.
- Clone this repository:
- Create and activate a virtualenv using `poetry shell`
- Install dependencies using `poetry install --with dev`
  - Note: you may have to remove `package-mode=false` on line 7 of `pyproject.toml`
- Install redis, rabbitmq-server, and postgresql 15 using your distro's package manager.
- Enable these services as background services using `sudo systemctl enable --now redis rabbitmq-server postgresql`
- Configure Postgres to ensure that password authentication is enabled for the gooey user
  - open the pg_hba.conf file in a text editor. On Linux, by default, it is usually located either at `/etc/postgresql/<version>/main/` or `/var/lib/pgsql/<version>/data/`
  - add/edit the file so that there are lines at the bottom that looks like this:
  ```
  local    all        gooey                    md5
  host     all        gooey                    md5
  ```

  - restart postgresql using `sudo systemctl restart postgresql`
- Use the manage.py script to set up the Postgres database:
  - To create the user and database for gooey: `./manage.py sqlcreate | sudo -u postgres psql postgres `
  - Test your setup to ensure that `gooey-server` can access the database by running `psql -W -U gooey gooey` and supplying "gooey" as the password
- Install the zbar library using your distro's package manager.

### 🗄 Initialize databse

```bash
# reset the database
./manage.py reset_db -c
# create the database
./manage.py sqlcreate | psql postgres
# run migrations
./manage.py migrate
# load the fixture (donwloaded by ./scripts/run-tests.sh)
./manage.py loaddata fixture.json
# create a superuser to access admin
./manage.py createsuperuser
```

### 🧪 Run Tests

```
ulimit -n unlimited  # Increase the number of open files allowed
./scripts/run-tests.sh
```

### ⚙️ Functions runtime (Cloudflare Workers)

The Functions recipe executes user-supplied JavaScript on [Cloudflare Workers](https://developers.cloudflare.com/workers/) (`functions/executor.js`). The executor wraps the user code in ES module code and runs it in an isolated worker via [dynamic Worker Loading](https://developers.cloudflare.com/workers/runtime-apis/bindings/worker-loader/), so plain expressions (e.g. an anonymous function) can be evaluated.

Deploy it to your own Cloudflare account:

```bash
npx wrangler deploy -c functions/wrangler.toml
npx wrangler secret put GOOEY_AUTH_TOKEN -c functions/wrangler.toml
```

For local development, run it with `npx wrangler dev -c functions/wrangler.toml`.

Then point Gooey Server at it in `.env`:

```env
CLOUDFLARE_FUNCTIONS_URL=https://gooey-functions.<your-subdomain>.workers.dev
CLOUDFLARE_FUNCTIONS_AUTH_TOKEN=your-secret  # i.e. the GOOEY_AUTH_TOKEN worker secret
```

### 🔌 Other non-essential features

Several features are opt-in and only appear when the relevant API keys are configured:

- **AI models** — each model provider (OpenAI, Anthropic, Replicate, etc.) is shown in the UI only when its API key is present.
- **Composio integrations** — the Composio tools selector is shown only when `COMPOSIO_API_KEY` is set.
- **Bot deployments** — WhatsApp and Twilio voice/SMS require `FB_APP_ID` / `TWILIO_ACCOUNT_SID`; Slack requires `SLACK_CLIENT_ID`. The deploy buttons are hidden and creation is blocked until the relevant keys are configured.

See [configuration.md](configuration.md) for the full list of keys and their defaults.

## 📐 Code Formatting

Use [ruff](https://docs.astral.sh/ruff/)

## 🏃 Run

### Services

These are the services that you need to run to start developing locally. Open them in separate terminals so you can debug them individually.

| Service                 | Port   | Command                                                                                                                                   |
| ----------------------- | ------ | ----------------------------------------------------------------------------------------------------------------------------------------- |
| Python API + GUI Server | `8080` | `poetry run uvicorn server:app --host 127.0.0.1 --port 8080 --reload`                                                                     |
| Node Frontend           | `3000` | `cd gooey-gui/; PORT=3000 REDIS_URL=redis://localhost:6379 npm run build && npm run start`                                                |
| Celery (Task Runner)    | -      | `poetry run celery -A celeryapp worker -P threads -c 16 -l DEBUG`                                                                         |
| Django Admin site       | `8000` | `poetry run python manage.py runserver 127.0.0.1:8000`                                                                                    |
| Vespa (Vector DB)       | `8085` | `docker run --hostname vespa-container -p 8085:8080 -p 19071:19071 --volume vespa:/opt/vespa/var -it --rm --name vespa vespaengine/vespa` |

This default startup assumes that Redis, RabbitMQ, and PostgreSQL are installed and running
as background services on ports `6379`, `5672`, and `5432` respectively.

The frontend source lives at `./gooey-gui/` inside this repo.

### Reloading on code changes

- The Python API + GUI Server should reload the entire server on code changes. You can refresh the page to see the changes.

- The Celery worker must be manually restarted on code changes.

- If you are working on the gooey-gui (react frontend), you can run:

```shell
cd gooey-gui/; PORT=3000 REDIS_URL=redis://localhost:6379 npm run dev
```

#### Hot Reloading

If you run this command, the Python API + GUI Server will reload the webpage in-place on code changes.

```shell
poetry run python server.py
```

This mostly works, but consumes more memory and usually OOMs after a few reloads; YMMV. Use it to iterate quickly on UI changes!

### Vespa (used for vector search)

You need to install OrbStack or Docker Desktop for this to work.

1. Create a persistent volume for Vespa:

```bash
docker volume create vespa
```

2. Run the container:

```bash
docker run \
  --hostname vespa-container \
  -p 8085:8080 -p 19071:19071 \
  --volume vespa:/opt/vespa/var \
  -it --rm --name vespa vespaengine/vespa
```

3. Run the setup script

```bash
./manage.py runscript setup_vespa_db
```

### Honcho

> [!CAUTION]
> This method is not recommended as this makes it harder to debug individual services but it is the easiest way to start all services at once.

You can start all required processes in one command with Honcho:

```shell
poetry run honcho start
```

The processes that it starts are defined in [`Procfile`](Procfile). You can open the Procfile and comment out any services you don't need to run.

This will spin up the API server at `http://localhost:8080`. To view the autogenerated API documentation, navigate to `http://localhost:8080/docs`

## 💣 Secret Scanning

Gitleaks will automatically run pre-commit (see `pre-commit-config.yaml` for details) to prevent commits with secrets in the first place. To test this without committing, run `pre-commit` from the terminal. To skip this check, use `SKIP=gitleaks git commit -m "message"` to commit changes. Preferably, label false positives with the `#gitleaks:allow` comment instead of skipping the check.

Gitleaks will also run in the CI pipeline as a GitHub action on push and pull request (can also be manually triggered in the actions tab on GitHub). To update the baseline of ignored secrets, run `python ./scripts/create_gitleaks_baseline.py` from the venv and commit the changes to `.gitleaksignore`.

## Privacy Policy

Click to know more about our [Privacy and Zero Data Retention Policy](https://gooey.ai/privacy).

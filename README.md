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
Gooey.AI is a low-code AI recipe platform and Gooey Server is our core repo. It allows users to discover, customize, and deploy AI "recipes" using the best of private and open-source AI, all using a single API with a single auth token. Recipes are workflows that incorporate various models to accomplish a task; they are designed to be highly customizable and shareable. 

## 🧑‍💻 Who is this for and why would I want to use it?
For most developers, we DO NOT recommend running or forking Gooey Server; use our [APIs](https://gooey.ai/api/) or [client SDK](https://github.com/GooeyAI/python-sdk) instead. The repo is intended only for developers who want to run and deploy their own server cluster or run Gooey locally for development purposes. Specifically, this repo may be for you if:
You want to create a new recipe (instead of changing the parameters on an existing one)
You want to add an AI model that we currently don’t support. 
You are an enterprise with specific requirements regarding data practices, such as using specific cloud providers.
You want to add some other functionality that we don’t support.

### 📋 Prerequisites
Google JSON key - only for auth / storage. 
Updated DB fixture
OS: Mac or Linux. Likely works on other *nix, but this is untested. 

### 🛠️ Issues that contributors could work on:
Firebase / Supabase migration. 
Provide a simpler workaround for localhost auth. 
Provide an open source alternative to Google auth for use in VPC. 
Provide a way to do storage locally. 

## 💻 Setup (Mac)

* Install [pyenv](https://github.com/pyenv/pyenv) & install the same python version as in our [Dockerfile](Dockerfile)
* Install [poetry](https://python-poetry.org/docs/)
* Clone the github repo to gooey-server (and make sure that's the folder name)
* Create & activate a virtualenv (e.g. `poetry shell`)
* Run `poetry install --with dev`
* Install [redis](https://redis.io/docs/getting-started/installation/install-redis-on-mac-os/), [rabbitmq](https://www.rabbitmq.com/install-homebrew.html), and [postgresql](https://formulae.brew.sh/formula/postgresql@15) (e.g. `brew install redis rabbitmq postgresql@15`)
* Enable background services for `redis`, `rabbitmq`, and `postgresql` (e.g. with `brew services start redis` and similar for `rabbitmq` and `postgresql`)
* Use `sqlcreate` helper to create a user and database for gooey:
  * `./manage.py sqlcreate | psql postgres`
  * make sure you are able to access the database with `psql -W -U gooey gooey` (and when prompted for password, entering `gooey`)
* Create an `.env` file from `.env.example` (Read [12factor.net/config](https://12factor.net/config))
* Run `./manage.py migrate`
* Install the zbar library (`brew install zbar`)

## 🐧 Setup (Linux)
* Install [pyenv](https://github.com/pyenv/pyenv) & install the same python version as in our [Dockerfile](Dockerfile) (currently Python 3.10)
  - `curl https://pyenv.run | bash`
* Install [poetry](https://python-poetry.org/docs/)
  - This is likely available in your distro's package repos. 
* Clone the gooey-server repository:
  - `git clone https://github.com/GooeyAI/gooey-server.git`
* If you want to use the web application frontend, you must clone that repo as well, in the same directory as gooey-server:
  - `git clone https://github.com/GooeyAI/gooey-ui`
* Create and activate a virtualenv using `poetry shell`
* Install dependencies using `poetry install --with dev`
  - Note: you may have to remove `package-mode=false` on line 7 of `pyproject.toml`
* Install redis, rabbitmq-server, and postgresql 15 using your distro's package manager. 
* Enable these services as background services using `sudo systemctl enable --now redis rabbitmq-server postgresql`
* Configure Postgres to ensure that password authentication is enabled for the gooey user
    - open the pg_hba.conf file in a text editor. On Linux, by default, it is usually located either at ```/etc/postgresql/<version>/main/``` or ```/var/lib/pgsql/<version>/data/```
    - add/edit the file so that there are lines at the bottom that looks like this:
    ```
    local    all        gooey                    md5
    host     all        gooey                    md5
    ```
    - restart postgresql using ```sudo systemctl restart postgresql```
* Use the manage.py script to set up the Postgres database:
  - To create the user and database for gooey: `./manage.py sqlcreate | sudo -u postgres psql postgres `
  - Test your setup to ensure that gooey-server can access the database by running `psql -W -U gooey gooey` and supplying "gooey" as the password
* Create a .env file from `.env.example`
* Install the zbar library using your distro's package manager. 

## 🏃 Run

Note: The gooey-server project is not currently set up to be run without support from Gooey. This software requires access to a Google Cloud instance as well as business data loaded in the database. If you are interested in running this software totally independently, reach out to support@gooey.ai to communicate with our enterprise team. 

You can start all required processes in one command with Honcho:

```shell
$ poetry run honcho start
```
This will spin up the API server at `http://localhost:8080`. To view the autogenerated API documentation, navigate to `http://localhost:8080/docs`

If you installed the gooey-ui server, you can navigate to 'http://localhost:3000' to access the web application.

The processes that it starts are defined in [`Procfile`](Procfile).
Currently they are these:

| Service          | Port    |
|------------------|---------|
| API + GUI Server | `8080`  |
| Admin site       | `8000`  |
| Usage dashboard  | `8501`  |
| Celery           | -       |
| UI               | `3000`  |
| Vespa            | `8085`  |

This default startup assumes that Redis, RabbitMQ, and PostgreSQL are installed and running
as background services on ports 6379, 5672, and 5432 respectively. 
It also assumes that the gooey-ui repo can be found at `../gooey-ui/` (adjacent to where the
gooey-server repo sits). You can open the Profile and comment this out if you don't need
to run it.

**Note:** the Celery worker must be manually restarted on code changes. You
can do this by stopping and starting Honcho.

### 📜 To run any recipe 

* In order to run recipes, you will need API keys. To connect to Gooey's Google Cloud instance, you need a personal key, stored in `serviceAccountKey.json` in the project root. 

### 🛵 To run vespa (used for vector search)

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

###  🖼️ Install imagemagick

Needed for HEIC image support - https://docs.wand-py.org/en/0.5.7/guide/install.html

```
brew install freetype imagemagick
export MAGICK_HOME=/opt/homebrew
```

### 📐 Code Formatting

Use black - https://pypi.org/project/black

**Recommended**: Black IDE integration Guide: [Pycharm](https://black.readthedocs.io/en/stable/integrations/editors.html#pycharm-intellij-idea)


### 🗄️ backup & restore postgres db

```bash
# reset the database
./manage.py reset_db -c
# create the database with an empty template
createdb -T template0 $PGDATABASE
# restore the database
pg_restore --no-privileges --no-owner -d $PGDATABASE $fname
```

### 🧩 create & load fixtures

```bash
./scripts/run-tests.sh
```

To load the fixture on local db -

```bash
# reset the database
./manage.py reset_db -c
# create the database
./manage.py sqlcreate | psql postgres
# run migrations
./manage.py migrate
# load the fixture
./manage.py loaddata fixture.json
# create a superuser to access admin
./manage.py createsuperuser
```

### 📋➡️💾 copy one postgres db to another

```bash
./manage.py reset_db
createdb -T template0 $PGDATABASE
pg_dump $SOURCE_DATABASE | psql -q $PGDATABASE
```


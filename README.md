## What is Gooey Server?
Gooey.AI is a low-code AI recipe platform and Gooey Server is our core repo.   
It allows users to discover, customize, and deploy AI "recipes" using the best of private and open source AI, 
all using a single API with a single auth token.   
Recipes are workflows that incorporate various models to accomplish a task; they are designed to be highly customizable and shareable. 

### Who is this for and why would I want to use it?
For the vast majority of developers, we DO NOT recommend running or forking Gooey Server; use our APIs or client SDK instead. 
The repo is intended only for developers that want to run and deploy their own server cluster or run Gooey locally for development purposes. 

Specifically, this repo may be for you if:
- You want to create a new recipe (instead of changing the parameters on an existing one)
- You want to add an AI model that we currently don’t support. 
- You are an enterprise who has specific requirements regarding data practices, such as using specific cloud providers.
- You want to add some other functionality that we don’t support.

## Setup

### Create a google cloud / firebase account

1. Create a [google cloud](https://console.cloud.google.com/) project
2. Create a [firebase project](https://console.firebase.google.com/) (using the same google cloud project) 
3. Enable the following services:
   - [Firestore](https://console.firebase.google.com/project/_/firestore)
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
6. Add your project & bucket name to `.env`


### MacOS

* Install [pyenv](https://github.com/pyenv/pyenv) & install the same python version as in our [Dockerfile](Dockerfile)
* Install [poetry](https://python-poetry.org/docs/)
* Clone the github repo to `gooey-server` (and make sure that's the folder name)
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
* (optional) Install imagemagick - Needed for HEIC image support - https://docs.wand-py.org/en/0.5.7/guide/install.html
```
brew install freetype imagemagick
export MAGICK_HOME=/opt/homebrew
```

### Linux
* Install [pyenv](https://github.com/pyenv/pyenv) & install the same python version as in our [Dockerfile](Dockerfile) (currently Python 3.10)
  - `curl https://pyenv.run | bash`
* Install [poetry](https://python-poetry.org/docs/)
  - This is likely available in your distro's package repos. 
* Clone this repository:
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
  - Test your setup to ensure that `gooey-server` can access the database by running `psql -W -U gooey gooey` and supplying "gooey" as the password
* Create a .env file from `.env.example`
* Install the zbar library using your distro's package manager. 

### Frontend 

Clone [gooey-gui](https://github.com/GooeyAI/gooey-gui) repo, in the same directory as `gooey-server` and follow the setup steps.

### Run Tests

``` 
ulimit -n unlimited  # Increase the number of open files allowed
./scripts/run-tests.sh
```

### Initialize databse


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

## Run

_Note: The `gooey-server` project is not currently set up to be run without support from Gooey. This software requires access to a Google Cloud instance as well as business data loaded in the database. If you are interested in running this software totally independently, reach out to support@gooey.ai to communicate with our enterprise team._ 

### Services

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

### Honcho

You can start all required processes in one command with Honcho:

```shell
poetry run honcho start
```
This will spin up the API server at `http://localhost:8080`. To view the autogenerated API documentation, navigate to `http://localhost:8080/docs`

This default startup assumes that Redis, RabbitMQ, and PostgreSQL are installed and running
as background services on ports `6379`, `5672`, and `5432` respectively.

The gooey-gui repo should be cloned at `../gooey-gui/`
(adjacent to where the`gooey-server` repo sits). You can open the Procfile and comment this out if you don't need
to run it.

**Note:** the Celery worker must be manually restarted on code changes. You
can do this by stopping and starting Honcho.

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


### Code Formatting

Use black - https://pypi.org/project/black

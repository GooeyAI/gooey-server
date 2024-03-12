## Setup

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

## Run

You can start all required processes in one command with Honcho:

```shell
$ poetry run honcho start
```

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
gooey-server repo sits). You can open the Procfile and comment this out if you don't need
to run it.

**Note:** the Celery worker must be manually restarted on code changes. You
can do this by stopping and starting Honcho.

## To run any recipe 

* Save `serviceAccountKey.json` to project root

## To run vespa (used for vector search)

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

## To connect to our GPU cluster 

* Connect to k8s cluster -
```bash
gcloud container clusters get-credentials cluster-5 --zone us-central1-a
```

* Port-forward the rabbitmq and redis services -
```bash
kubectl port-forward rabbitmq-1-rabbitmq-0 15674:15672 5674:5672 & kubectl port-forward redis-ha-1-server-0 6374:6379
```

* Add the following to `.env` file -
```
GPU_CELERY_BROKER_URL="amqp://rabbit:<password>@localhost:5674"
GPU_CELERY_RESULT_BACKEND="redis://:<password>@localhost:6374"
```

### Install imagemagick

Needed for HEIC image support - https://docs.wand-py.org/en/0.5.7/guide/install.html

```
brew install freetype imagemagick
export MAGICK_HOME=/opt/homebrew
```

### Code Formatting

Use black - https://pypi.org/project/black

**Recommended**: Black IDE integration Guide: [Pycharm](https://black.readthedocs.io/en/stable/integrations/editors.html#pycharm-intellij-idea)


## Running test Whatsapp bot

We use the following facebook app for testing - 
```
gooey.ai (dev)
App ID: 228027632918921
```

Create a [meta developer account](https://developers.facebook.com/docs/development/register/) & send admin your **facebook ID** to add you to the test app [here](https://developers.facebook.com/apps/228027632918921/roles/roles/?business_id=549319917267066)

1. start ngrok

```
ngrok http 8080
```

2. set env var `FB_WEBHOOK_TOKEN = asdf1234`


3. Open [WhatsApp Configuration](https://developers.facebook.com/apps/228027632918921/whatsapp-business/wa-settings/?business_id=549319917267066), set the Callback URL and Verify Token
<img width="500" alt="image" src="https://github.com/GooeyAI/gooey-server/assets/19492893/95bb3a87-ae4f-4f6b-a04e-583ee51b85de">

4. Open [WhatsApp API Setup](https://developers.facebook.com/apps/228027632918921/whatsapp-business/wa-dev-console/?business_id=549319917267066), send yourself a message from the test number.
<img width="500" alt="image" src="https://github.com/GooeyAI/gooey-server/assets/19492893/f9417723-77c0-4be5-9814-778662215d9c">

5. Copy the temporary access token there and set env var `WHATSAPP_ACCESS_TOKEN = XXXX`


**(Optional) Use the test script to send yourself messages** 

```bash
python manage.py runscript test_wa_msg_send --script-args 104696745926402 +918764022384
```
Replace `+918764022384` with your number and `104696745926402` with the test number ID

## Dangerous postgres commands

### backup & restore postgres db

**on server**
```bash
# select a running container
cid=$(docker ps | grep gooey-api-prod | cut -d " " -f 1 | head -1)
# give it a nice name 
fname=gooey_db_$(date +"%Y-%m-%d_%I-%M-%S_%p").dump
# exec the script to create the fixture
docker exec -it $cid pg_dump --dbname $PGDATABASE --format c -f "$fname"
# copy the fixture outside container
docker cp $cid:/app/$fname .
# print the absolute path
echo $PWD/$fname
```

**on local**
```bash
# reset the database
./manage.py reset_db -c
# create the database with an empty template
createdb -T template0 $PGDATABASE
# restore the database
pg_restore --no-privileges --no-owner -d $PGDATABASE $fname
```

### create & load fixtures

**on server**
```bash
# select a running container
cid=$(docker ps  | grep gooey-api-prod | cut -d " " -f 1 | head -1)
# exec the script to create the fixture
docker exec -it $cid poetry run ./manage.py runscript create_fixture
```

```bash
# copy the fixture outside container
docker cp $cid:/app/fixture.json .
# print the absolute path
echo $PWD/fixture.json
```

**on local**
```bash
# copy fixture.json from server to local
rsync -P -a <username>@captain.us-1.gooey.ai:/home/<username>/fixture.json .
```

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

### copy one postgres db to another

**on server**
```bash
./manage.py reset_db
createdb -T template0 $PGDATABASE
pg_dump $SOURCE_DATABASE | psql -q $PGDATABASE
```

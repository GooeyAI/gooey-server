## Setup
* Install [pyenv](https://github.com/pyenv/pyenv) & install the same python version as in our [Dockerfile](Dockerfile)
* Install [poetry](https://python-poetry.org/docs/)
* Create & active a virtualenv (e.g. `poetry shell`)
* Run `poetry install --with dev`
* Create an `.env` file from `.env.example` (Read [12factor.net/config](https://12factor.net/config))
* Run `./manage.py migrate`

## Run

### API + GUI server

```bash
uvicorn server:app --host 0.0.0.0 --port 8080 --reload
```

Open [localhost:8080](localhost:8080) in your browser

### Admin Site

```bash
python3 manage.py runserver 0.0.0.0:8000
```

Open [localhost:8000](localhost:8000) in your browser


### Usage Dashboard

```
streamlit run Home.py --server.port 8501
```

Open [localhost:8501](localhost:8501) in your browser

## To run any recipe 

* Save `serviceAccountKey.json` to project root
* Install & start [redis](https://redis.io/docs/getting-started/installation/install-redis-on-mac-os/)
* Install & start [rabbitmq](https://www.rabbitmq.com/install-homebrew.html)
* Run the celery worker (**Note:** you must manually restart it on code changes)
```bash
celery -A celeryapp worker
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

```bash
# reset the database
./manage.py reset_db -c
# create the database with an empty template
createdb -T template0 $PGDATABASE
# restore the database
pg_restore --no-privileges --no-owner -d $PGDATABASE $fname
```

### create & load fixtures

```bash
# select a running container
cid=$(docker ps  | grep gooey-api-prod | cut -d " " -f 1 | head -1)
# exec the script to create the fixture
docker exec -it $cid poetry run ./manage.py runscript create_fixture
# copy the fixture outside container
docker cp $cid:/app/fixture.json .
# print the absolute path
echo $PWD/fixture.json
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
```

### copy one postgres db to another

```
./manage.py reset_db
createdb -T template0 $PGDATABASE
pg_dump $SOURCE_DATABASE | psql -q $PGDATABASE
```

## Setup
1. Install [Pyenv](https://github.com/pyenv/pyenv) & install python 3.10
2. Install [poetry](https://python-poetry.org/docs/)
4. Create & active a virtualenv (likely `poetry shell`)
5. Run `poetry install --with dev`
6. Create an `.env` file from `.env.example`

### Run

```bash
./scripts/run-dev.sh
```

Open `localhost:8080` in your browser

```
./manage.py runserver
```

Open `localhost:8000` in your browser


### To run & save recipes 

1. Save `serviceAccountKey.json` to project root (copy from Dara server project)

2. To connect to prod GPU cluster -
### Connect to k8s cluster -
```bash
gcloud container clusters get-credentials cluster-5 --zone us-central1-a
```
### Port-forward the rabbitmq and redis services -
```bash
kubectl port-forward rabbitmq-1-rabbitmq-0 15674:15672 5674:5672 & kubectl port-forward redis-ha-1-server-0 63791:
```
### Add the following to `.env` file -
```
CELERY_BROKER_URL="amqp://rabbit:<password>@localhost:5674"
CELERY_RESULT_BACKEND="redis://:<password>@localhost:63791"
```

### Install imagemagick

Needed for HEIC image support - https://docs.wand-py.org/en/0.5.7/guide/install.html

```
brew install freetype imagemagick
export MAGICK_HOME=/opt/homebrew
```

### Install black (code formatter)

Needed for uniform formatting - https://pypi.org/project/black

### Recommended:

Black IDE integration
Guide: [Pycharm](https://black.readthedocs.io/en/stable/integrations/editors.html#pycharm-intellij-idea)

### Our Colors

pink: #ff66c6
azure: #aae3ef

### Github self-hosted runner

#### additional installs on top of GCP ubuntu:18.04

```
apt-get install python3-venv ffmpeg libsm6 libxext6  -y
```

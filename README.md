### Setup


1. Install [poetry](https://python-poetry.org/docs/)
2. Run `poetry install --with dev`

3. Active virtualenv (likely `poetry shell`)
4. Copy `.env.example` -> `.env` (have someone send you the contents and then paste into the .env file)
5. Save `serviceAccountKey.json` to project root (copy from Dara server project)

6. run `pip install --upgrade -r requirements.txt` to get all the latest packages

##### Install imagemagick

Needed for HEIC image support - https://docs.wand-py.org/en/0.5.7/guide/install.html

```
brew install freetype imagemagick
export MAGICK_HOME=/opt/homebrew
```

### Run

`streamlit run Home.py`

### Our Colors
pink: #ff66c6
azure: #aae3ef

### Github self-hosted runner 
#### additional installs on top of GCP ubuntu:18.04
```
apt-get install python3-venv ffmpeg libsm6 libxext6  -y
```

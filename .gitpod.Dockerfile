# You can find the new timestamped tags here: https://hub.docker.com/r/gitpod/workspace-full/tags
FROM gitpod/workspace-full:2022-05-08-14-31-53

RUN pyenv install 3.10.3 && pyenv global 3.10.3

RUN sudo install-packages python3-opencv libmagickwand-dev ffmpeg nginx || true

RUN curl -sSL https://install.python-poetry.org | python3 -

ENV PATH ~/.local/bin:$PATH
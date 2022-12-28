# You can find the new timestamped tags here: https://hub.docker.com/r/gitpod/workspace-full/tags
FROM gitpod/workspace-python-3.10

RUN sudo install-packages python3-opencv libmagickwand-dev ffmpeg nginx

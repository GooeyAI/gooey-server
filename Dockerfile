# base python image
FROM library/python:3.10.12-slim-bookworm

# set the working directory in the container
ENV WORKDIR /app
WORKDIR $WORKDIR

# install latest poppler - https://poppler.freedesktop.org/
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    wget \
    cmake \
    libboost-dev \
    libmagickwand-dev \
    libgl1-mesa-glx \
	&& rm -rf /var/lib/apt/lists/*
RUN wget -qO- 'https://poppler.freedesktop.org/poppler-23.07.0.tar.xz' | tar -xJ -C poppler \
    && cd poppler \
    && cmake . \
    && ldconfig \
    && make install \
    && cd $WORKDIR \
    && rm -rf poppler

# install latest pandoc - https://github.com/jgm/pandoc/releases
RUN wget -qO pandoc.deb 'https://github.com/jgm/pandoc/releases/download/3.1.5/pandoc-3.1.5-1-amd64.deb' \
    && dpkg -i pandoc.deb \
    && rm pandoc.deb

# app dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-opencv \
    postgresql-client \
	ffmpeg \
    libzbar0 \
	&& rm -rf /var/lib/apt/lists/*

# copy poetry files
COPY ./pyproject.toml ./poetry.lock ./
# install python dependencies
RUN pip install --no-cache-dir -U poetry pip && poetry install --no-cache --only main --no-interaction

# copy the code into the container
COPY . .

ENV FORWARDED_ALLOW_IPS='*'
ENV PYTHONUNBUFFERED=1

EXPOSE 8000
EXPOSE 8501

CMD poetry run ./scripts/run-prod.sh

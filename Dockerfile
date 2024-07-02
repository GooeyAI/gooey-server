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
RUN wget -qO- 'https://poppler.freedesktop.org/poppler-23.07.0.tar.xz' | tar -xJ \
    && cd poppler-23.07.0 \
    && cmake . \
    && ldconfig \
    && make install \
    && cd $WORKDIR \
    && rm -rf poppler-23.07.0

# install latest pandoc - https://github.com/jgm/pandoc/releases
RUN wget -qO pandoc.deb 'https://github.com/jgm/pandoc/releases/download/3.2/pandoc-3.2-1-amd64.deb' \
    && dpkg -i pandoc.deb \
    && rm pandoc.deb

# app dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-opencv \
    postgresql-client \
	ffmpeg \
    libzbar0 \
	&& rm -rf /var/lib/apt/lists/*

# because https://github.com/Azure-Samples/cognitive-services-speech-sdk/issues/2204
RUN wget -qO libssl.deb http://security.ubuntu.com/ubuntu/pool/main/o/openssl/libssl1.1_1.1.1f-1ubuntu2.22_amd64.deb \
    && dpkg -i libssl.deb \
    && rm libssl.deb

# copy poetry files
COPY ./pyproject.toml ./poetry.lock ./
# install python dependencies
RUN pip install --no-cache-dir -U poetry pip && poetry install --no-cache --only main --no-interaction

# install nltk stopwords
RUN poetry run python -c 'import nltk; nltk.download("stopwords")'
# install playwright
RUN poetry run playwright install-deps && poetry run playwright install

# copy the code into the container
COPY . .

ENV FORWARDED_ALLOW_IPS='*'
ENV PYTHONUNBUFFERED=1

EXPOSE 8000
EXPOSE 8501

HEALTHCHECK CMD \
    wget 127.0.0.1:8000 \
    || wget 127.0.0.1:8501 \
    || bash -c 'poetry run celery -A celeryapp inspect ping -d celery@$HOSTNAME' \
    || exit 1

ENTRYPOINT ["poetry", "run"]
CMD ["./scripts/run-prod.sh"]

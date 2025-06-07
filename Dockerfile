# base python image
FROM library/python:3.10.12-slim-bookworm

ARG ARCH="arm64"

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
    python3-opencv \
    postgresql-client \
    ffmpeg \
    libzbar0 \
    && rm -rf /var/lib/apt/lists/*

# install latest pandoc - https://github.com/jgm/pandoc/releases
RUN wget -qO pandoc.deb "https://github.com/jgm/pandoc/releases/download/3.2/pandoc-3.2-1-$ARCH.deb" \
    && dpkg -i pandoc.deb \
    && rm pandoc.deb

# because https://github.com/Azure-Samples/cognitive-services-speech-sdk/issues/2204
RUN if [ "$ARCH" = "arm64" ]; then \
      wget -qO libssl.deb "http://ftp.de.debian.org/debian/pool/main/o/openssl/libssl1.1_1.1.1w-0+deb11u1_arm64.deb" \
    ; else \
      wget -qO libssl.deb "http://archive.ubuntu.com/ubuntu/pool/main/o/openssl/libssl1.1_1.1.0g-2ubuntu4_amd64.deb" \
    ; fi \
    && dpkg -i libssl.deb \
    && rm libssl.deb

RUN wget -qO- 'https://poppler.freedesktop.org/poppler-23.07.0.tar.xz' | tar -xJ \
    && cd poppler-23.07.0 \
    && cmake . \
    && ldconfig \
    && make install \
    && cd $WORKDIR \
    && rm -rf poppler-23.07.0

# copy poetry files
COPY ./pyproject.toml ./poetry.lock ./
# install python dependencies
RUN pip install --no-cache-dir -U poetry pip && poetry install --no-cache --only main --no-interaction

# install playwright
RUN poetry run playwright install-deps && poetry run playwright install chromium

# copy the code into the container
COPY . .

ENV FORWARDED_ALLOW_IPS='*'
ENV PYTHONUNBUFFERED=1

ARG CAPROVER_GIT_COMMIT_SHA=${CAPROVER_GIT_COMMIT_SHA}
ENV CAPROVER_GIT_COMMIT_SHA=${CAPROVER_GIT_COMMIT_SHA}

EXPOSE 8000
EXPOSE 8501

HEALTHCHECK CMD \
    wget 127.0.0.1:8000 \
    || wget 127.0.0.1:8000/status \
    || wget 127.0.0.1:8501 \
    || bash -c 'poetry run celery -A celeryapp inspect ping -d celery@$HOSTNAME' \
    || exit 1

ENTRYPOINT ["poetry", "run"]
CMD ["./scripts/run-prod.sh"]

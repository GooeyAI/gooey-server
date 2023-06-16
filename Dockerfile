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
    libgl1-mesa-glx
RUN wget -qO- 'https://poppler.freedesktop.org/poppler-23.05.0.tar.xz' | tar -xJ \
    && cd poppler-23.05.0 \
    && cmake . \
    && ldconfig \
    && make install \
    && cd $WORKDIR \
    && rm -rf poppler-23.05.0

# app dependencies
RUN apt-get install -y --no-install-recommends \
    python3-opencv \
    pandoc \
    postgresql-client \
	ffmpeg

RUN rm -rf /var/lib/apt/lists/*

# copy poetry files
COPY ./pyproject.toml ./poetry.lock ./
# install python dependencies
RUN pip install -U poetry pip && poetry install --only main --no-interaction

# copy the code into the container
COPY . .

ENV FORWARDED_ALLOW_IPS='*'
ENV PYTHONUNBUFFERED=1

EXPOSE 8000
EXPOSE 8501

CMD poetry run ./scripts/run-prod.sh

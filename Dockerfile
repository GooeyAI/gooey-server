FROM library/python:3.10-slim

EXPOSE 8000

ENV WORKDIR /usr/src/app
RUN mkdir -p $WORKDIR
WORKDIR $WORKDIR

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-opencv \
    libmagickwand-dev \
    build-essential libpoppler-cpp-dev \
	&& rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt

COPY . .

RUN python scripts/fix_st_timeout.py

ENV FORWARDED_ALLOW_IPS='*'
ENV PYTHONUNBUFFERED=1

EXPOSE 8501

CMD ./scripts/run-prod.sh

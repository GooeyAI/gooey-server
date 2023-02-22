FROM library/python:3.10-slim

EXPOSE 8000

ENV WORKDIR /usr/src/app
RUN mkdir -p $WORKDIR
WORKDIR $WORKDIR

RUN apt-get update && apt-get install -y python3-opencv libmagickwand-dev libpoppler-cpp-dev

COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt

COPY . .

RUN python scripts/fix_st_timeout.py

ENV FORWARDED_ALLOW_IPS='*'
ENV PYTHONUNBUFFERED=1

EXPOSE 8501

CMD ./scripts/run-prod.sh

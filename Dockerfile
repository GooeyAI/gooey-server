FROM library/python:3.10-slim

EXPOSE 8000

ENV WORKDIR /usr/src/app
RUN mkdir -p $WORKDIR
WORKDIR $WORKDIR

RUN apt-get update && apt-get install -y libgl1

COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt

COPY . .

ENV FORWARDED_ALLOW_IPS '*'

CMD ./scripts/run-prod.sh

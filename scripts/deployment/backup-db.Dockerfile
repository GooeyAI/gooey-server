FROM postgres:15

WORKDIR /app
COPY ../backup-db.sh /app/backup-db.sh

RUN apt-get update && apt-get install -y cron

RUN chmod 0744 /app/backup-db.sh
RUN echo "0 4 * * * /app/backup-db.sh" | crontab -

CMD ["cron"]

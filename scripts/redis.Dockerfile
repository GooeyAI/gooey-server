FROM redis:7

HEALTHCHECK CMD \
    bash -c 'redis-cli -a $REDIS_PASSWORD ping | grep PONG'

CMD bash -c 'redis-server /data/redis.conf --requirepass $REDIS_PASSWORD'

FROM redis:7

CMD bash -c 'redis-server /data/redis.conf --requirepass $REDIS_PASSWORD'

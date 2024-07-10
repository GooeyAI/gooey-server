FROM redis:7

# we don't want to use redis.conf so pass env vars to redis-server
# NOTE: these are runtime environment variables! not needed when building the image
CMD bash -c 'redis-server --requirepass $REDIS_PASSWORD --maxmemory $REDIS_MAXMEMORY --maxmemory-policy $REDIS_MAXMEMORY_POLICY --bind $REDIS_BIND'

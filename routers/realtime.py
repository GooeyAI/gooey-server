# import json
# import pickle
# import uuid
#
# import redis
# import redis.asyncio
#
# import gooey_ui as st
# from daras_ai_v2 import settings
#
#
# @st.cache_resource
# def get_redis():
#     return redis.Redis.from_url(settings.REDIS_URL)
#
#
# def realtime_set(redis_key: str, value=None, expire=None):
#     r = get_redis()
#     r.publish(redis_key, json.dumps(value))
#     # if not redis_key:
#     #     redis_key = f"__realtime/{uuid.uuid1()}"
#     #     st.session_state["__realtime_key"] = redis_key
#     # else:
#     #     redis_key = redis_key
#     #
#     # r = get_redis()
#     # r.publish(redis_key, "ping")
#     # if value is not None:
#     #     r.set(redis_key, pickle.dumps(value))
#     # if expire is not None:
#     #     r.expire(redis_key, expire)

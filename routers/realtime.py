import pickle
import uuid

import redis
import redis.asyncio
import streamlit as st
from fastapi import APIRouter
from furl import furl
from starlette.responses import StreamingResponse

from daras_ai_v2 import settings
from mycomponent import pubsub_component

router = APIRouter()


@router.get("/key-events", include_in_schema=False)
async def key_events(topic: str):
    async def stream():
        r = redis.asyncio.Redis.from_url(settings.REDIS_URL)
        async with r.pubsub() as pubsub:
            await pubsub.subscribe(topic)
            async for _ in pubsub.listen():
                yield "data: pong\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@st.experimental_singleton
def get_redis():
    return redis.Redis.from_url(settings.REDIS_URL)


def get_key_events_url(redis_key: str) -> furl:
    return furl(
        settings.API_BASE_URL, query_params={"topic": redis_key}
    ) / router.url_path_for(key_events.__name__)


def realtime_subscribe(redis_key: str = None):
    if not redis_key:
        redis_key = f"__realtime/{uuid.uuid1()}"
        st.session_state["__realtime_key"] = redis_key
    else:
        redis_key = redis_key

    pubsub_component(url=str(get_key_events_url(redis_key)))

    r = get_redis()
    value = r.get(redis_key)
    if not value:
        return
    return pickle.loads(value)


def realtime_set(redis_key: str = None, value=None, expire=None):
    if not redis_key:
        redis_key = f"__realtime/{uuid.uuid1()}"
        st.session_state["__realtime_key"] = redis_key
    else:
        redis_key = redis_key

    r = get_redis()
    r.publish(redis_key, "ping")
    if value is not None:
        r.set(redis_key, pickle.dumps(value))
    if expire is not None:
        r.expire(redis_key, expire)

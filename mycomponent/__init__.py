import json
import uuid

import redis
import streamlit as st
import streamlit.components.v1 as components

from daras_ai_v2 import settings
from routers.realtime import get_key_events_url

_mycomponent = components.declare_component("mycomponent", path="./mycomponent")


@st.experimental_singleton
def get_redis():
    return redis.Redis.from_url(settings.REDIS_URL)


def reloader_sub(key: str):
    if key not in st.session_state:
        st.session_state[key] = f"{key}/{uuid.uuid1()}"
    redis_key = st.session_state[key]
    url = str(get_key_events_url(redis_key))
    _mycomponent(url=url)
    # r = get_redis()
    # value = r.get(redis_key)
    # return value


def reloader_pub(key: str, value=None):
    if key not in st.session_state:
        st.session_state[key] = f"{key}/{uuid.uuid1()}"
    redis_key = st.session_state[key]
    r = get_redis()
    r.publish(redis_key, "ping")
    # if value is not None:
    #     r.set(redis_key, json.dumps(value))

import json
import uuid

import redis
import streamlit.components.v1 as components
from furl import furl
import streamlit as st

from daras_ai_v2 import settings

_mycomponent = components.declare_component("mycomponent", path="./mycomponent")


def reloader_recv(key: str):
    if key not in st.session_state:
        st.session_state[key] = f"__reloader_{uuid.uuid1()}"
    redis_key = st.session_state[key]
    f = furl(settings.API_BASE_URL) / "key-events" / redis_key
    if not _mycomponent(url=str(f), key=str(f)):
        return
    r = redis.Redis()
    value = r.get(redis_key)
    if not value:
        return
    return json.loads(value)


def reloader_send(key: str, value=0):
    r = redis.Redis()
    redis_key = st.session_state[key]
    r.set(redis_key, json.dumps(value))
    r.publish(redis_key, b"")

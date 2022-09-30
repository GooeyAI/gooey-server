import json

import requests
import streamlit as st

from daras_ai.components.core import daras_ai_step


@daras_ai_step("Training data via HTTP")
def http_data_source(variables, state, set_state):
    method = st.text_input(
        label="HTTP method",
        value=state.get("method", ""),
    )
    set_state({"method": method})

    url = st.text_input(
        label="URL",
        value=state.get("url", ""),
    )
    set_state({"url": url})

    headers = st.text_area(
        label="Headers",
        value=state.get("headers", "{}"),
    )
    set_state({"headers": headers})

    json_body = st.text_area(
        label="JSON body",
        value=state.get("json_body", ""),
    )
    set_state({"json_body": json_body})

    "**Response**"

    if "data_source_response" not in st.session_state:
        with st.spinner():
            r = requests.request(
                method,
                url,
                headers=json.loads(headers),
                json=json.loads(json_body),
            )
    r.raise_for_status()
    response_json = r.json()

    st.write(response_json)

    out_var = st.text_input(
        label="Output var",
        value=state.get("out_var"),
    )
    if out_var is not None:
        set_state({"out_var": out_var})
        variables[out_var] = response_json

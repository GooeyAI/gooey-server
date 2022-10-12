import json
from locale import format

import requests
import streamlit as st

from daras_ai.core import daras_ai_step_config, daras_ai_step_computer
from daras_ai.text_format import daras_ai_format_str


@daras_ai_step_config("Call External API")
def http_data_source(idx, variables, state):
    method = st.text_input(
        label="HTTP method",
        value=state.get("method", ""),
    )
    state.update({"method": method})

    url = st.text_input(
        label="URL",
        value=state.get("url", ""),
    )
    state.update({"url": url})

    headers = st.text_area(
        label="Headers",
        value=state.get("headers", "{}"),
    )
    state.update({"headers": headers})

    json_body = st.text_area(
        label="JSON body",
        value=state.get("json_body", ""),
    )
    state.update({"json_body": json_body})

    output_var = st.text_input(
        label="Output Variable",
        value=state.get("output_var", ""),
    )
    state.update({"output_var": output_var})

    st.write("Output Data (fetched)")
    st.write(variables.get(output_var, ""))


@daras_ai_step_computer
def http_data_source(idx, variables, state):
    json_body = state["json_body"]
    method = state["method"]
    url = state["url"]
    headers = state["headers"]
    output_var = state["output_var"]

    url = daras_ai_format_str(url, variables)

    if not (url and method and output_var):
        raise ValueError

    if headers:
        headers = daras_ai_format_str(headers, variables)
        headers = json.loads(headers)
    else:
        headers = None

    if json_body:
        json_body = daras_ai_format_str(json_body, variables)
        body = json.loads(json_body)
    else:
        body = None

    with st.spinner():
        r = requests.request(
            method,
            url,
            headers=headers,
            json=body,
        )

    r.raise_for_status()
    response_json = r.json()

    variables[output_var] = response_json

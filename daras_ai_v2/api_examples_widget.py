import json
import shlex
from textwrap import indent

import black
import streamlit as st
from furl import furl

from daras_ai_v2.doc_search_settings_widgets import is_user_uploaded_url
from gooey_token_authentication1.token_authentication import auth_keyword


def get_filenames(request_body):
    for key, value in request_body.items():
        if not isinstance(value, list):
            value = [value]
        if not (value and isinstance(value[0], str) and value[0].startswith("http")):
            continue
        for item in value:
            if not is_user_uploaded_url(item):
                continue
            yield key, furl(item).path.segments[-1]


def api_example_generator(api_url: furl, request_body: dict, upload_files: bool):
    curl, python, js = st.tabs(["curl", "python", "node.js"])

    filenames = []
    if upload_files:
        filenames = list(get_filenames(request_body))
        for key, _ in filenames:
            request_body.pop(key, None)
    if filenames:
        api_url /= "form/"
    api_url = str(api_url)

    with curl:
        st.write(
            """
```bash
export GOOEY_API_KEY=sk-xxxx
```
            """
        )

        if filenames:
            st.write(
                r"""
```bash
curl %s \
  -H "Authorization: %s $GOOEY_API_KEY" \
  %s \
  -F json=%s
```
                """
                % (
                    shlex.quote(api_url),
                    auth_keyword,
                    " \\\n  ".join(
                        f"-F {key}=@{shlex.quote(filename)}"
                        for key, filename in filenames
                    ),
                    shlex.quote(json.dumps(request_body, indent=2)),
                )
            )
        else:
            st.write(
                r"""
```bash
curl %s \
  -H 'Content-Type: application/json' \
  -H "Authorization: %s $GOOEY_API_KEY" \
  -d %s
```
            """
                % (
                    shlex.quote(api_url),
                    auth_keyword,
                    shlex.quote(json.dumps(request_body, indent=2)),
                )
            )

    with python:
        st.write(
            r"""
```bash
$ python3 -m pip install requests
$ export GOOEY_API_KEY=sk-xxxx
```    
             """
        )

        if filenames:
            py_code = r"""
import os
import requests
import json

files = [%s,]
data = %s

response = requests.post(
    "%s",
    headers={
        "Authorization": "%s " + os.environ["GOOEY_API_KEY"],
    },
    files=files,
    data={"json": json.dumps(data)},
)

data = response.json()
print(response.status_code, data)
            """ % (
                ",".join(f'({key!r}, open({name!r}, "rb"))' for key, name in filenames),
                repr(request_body),
                api_url,
                auth_keyword,
            )
        else:
            py_code = r"""
import os
import requests

response = requests.post(
    "%s",
    headers={
        "Authorization": "%s " + os.environ["GOOEY_API_KEY"],
    },
    json=%s,
)

data = response.json()
print(response.status_code, data)
            """ % (
                api_url,
                auth_keyword,
                repr(request_body),
            )
        st.write(
            f"""
```python
{black.format_str(py_code, mode=black.FileMode())}
```
            """
        )

    with js:
        st.write(
            r"""
```
$ npm install node-fetch
```
```js
import fetch from 'node-fetch';
```
```js
async function callApi() {
  const response = await fetch("%s", {
    method: "POST",
    headers: {
        "Authorization": "%s $GOOEY_API_KEY",
        "Content-Type": "application/json",
    },
    body: JSON.stringify(%s),
  });

  const data = await response.json();
  console.log(response.status, data);
}

callApi();
```
            """
            % (
                api_url,
                auth_keyword,
                indent(json.dumps(request_body, indent=2), " " * 4)[4:],
            )
        )

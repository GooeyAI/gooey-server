import json
import shlex
from textwrap import indent

import streamlit as st

from gooey_token_authentication1.token_authentication import auth_keyword


def api_example_generator(api_url: str, request_body):
    curl, python, js = st.tabs(["`curl`", "`python`", "`node.js`"])

    with curl:
        st.write(
            r"""
```bash
curl -X 'POST' \
  %s \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -H 'Authorization: %s $GOOEY_API_KEY' \
  -d %s
```
            """
            % (api_url, auth_keyword, shlex.quote(json.dumps(request_body, indent=2)))
        )

    with python:
        st.write(
            r"""
```
$ python3 -m pip install requests
```    

```python
import requests

response = requests.post(
    "%s",
    headers={
        "Authorization": "%s $GOOEY_API_KEY",
    },
    json=%s,
)

data = response.json()
print(response.status_code, data)
```
            """
            % (
                api_url,
                auth_keyword,
                indent(json.dumps(request_body, indent=4), " " * 4)[4:],
            )
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

import json
import shlex
from textwrap import indent

import gooey_ui as st
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


def api_example_generator(api_url: furl, request_body: dict, as_form_data: bool):
    js, python, curl = st.tabs(["`node.js`", "`python`", "`curl`"])

    filenames = []
    if as_form_data:
        filenames = list(get_filenames(request_body))
        for key, _ in filenames:
            request_body.pop(key, None)
        api_url /= "form/"
    api_url = str(api_url)

    with curl:
        if as_form_data:
            curl_code = r"""
curl %(api_url)s \
  -H "Authorization: %(auth_keyword)s $GOOEY_API_KEY" \
  %(files)s \
  -F json=%(json)s
                """ % dict(
                api_url=shlex.quote(api_url),
                auth_keyword=auth_keyword,
                files=" \\\n  ".join(
                    f"-F {key}=@{shlex.quote(filename)}" for key, filename in filenames
                ),
                json=shlex.quote(json.dumps(request_body, indent=2)),
            )
        else:
            curl_code = r"""
curl %(api_url)s \
  -H "Authorization: %(auth_keyword)s $GOOEY_API_KEY" \
  -H 'Content-Type: application/json' \
  -d %(json)s
            """ % dict(
                api_url=shlex.quote(api_url),
                auth_keyword=auth_keyword,
                json=shlex.quote(json.dumps(request_body, indent=2)),
            )
        st.write(
            """
1. Generate an api key [below👇](#api-keys)

2. Install [curl](https://everything.curl.dev/get) & add the `GOOEY_API_KEY` to your environment variables.  
Never store the api key [in your code](https://12factor.net/config).          
```bash
export GOOEY_API_KEY=sk-xxxx
```

3. Run the following `curl` command in your terminal.  
If you encounter any issues, write to us at support@gooey.ai and make sure to include the full curl command and the error message.
```bash
%s
```
            """
            % curl_code.strip()
        )

    with python:
        if as_form_data:
            py_code = r"""
import os
import requests
import json

files = [%(files)s]
payload = %(json)s

response = requests.post(
    "%(api_url)s",
    headers={
        "Authorization": "%(auth_keyword)s " + os.environ["GOOEY_API_KEY"],
    },
    files=files,
    data={"json": json.dumps(payload)},
)

result = response.json()
print(response.status_code, result)
            """ % dict(
                files=",".join(
                    f'({key!r}, open({name!r}, "rb"))' for key, name in filenames
                ),
                json=repr(request_body),
                api_url=api_url,
                auth_keyword=auth_keyword,
            )
        else:
            py_code = r"""
import os
import requests

payload = %(json)s

response = requests.post(
    "%(api_url)s",
    headers={
        "Authorization": "%(auth_keyword)s " + os.environ["GOOEY_API_KEY"],
    },
    json=payload,
)

result = response.json()
print(response.status_code, result)
            """ % dict(
                api_url=api_url,
                auth_keyword=auth_keyword,
                json=repr(request_body),
            )
        import black

        py_code = black.format_str(py_code, mode=black.FileMode())
        st.write(
            rf"""
1. Generate an api key [below👇](#api-keys)

2. Install [requests](https://requests.readthedocs.io/en/latest/) & add the `GOOEY_API_KEY` to your environment variables.  
Never store the api key [in your code](https://12factor.net/config).          
```bash
$ python3 -m pip install requests
$ export GOOEY_API_KEY=sk-xxxx
```
    
3. Use this sample code to call the API.    
If you encounter any issues, write to us at support@gooey.ai and make sure to include the full code snippet and the error message.
```python
%s
```
            """
            % py_code
        )

    with js:
        if as_form_data:
            js_code = """\
import fetch, { FormData, fileFrom } from 'node-fetch';

const payload = %(json)s;

async function gooeyAPI() {
  const formData = new FormData()
  formData.set('json', JSON.stringify(payload))
%(files)s

  const response = await fetch("%(api_url)s", {
    method: "POST",
    headers: {
        "Authorization": "%(auth_keyword)s " + process.env["GOOEY_API_KEY"],
    },
    body: formData,
  });

  const result = await response.json();
  console.log(response.status, result);
}

gooeyAPI();
            """ % dict(
                json=json.dumps(request_body, indent=2),
                files=indent(
                    "\n".join(
                        "formData.append(%r, await fileFrom(%r)" % (key, name)
                        for key, name in filenames
                    ),
                    " " * 2,
                ),
                api_url=api_url,
                auth_keyword=auth_keyword,
            )

        else:
            js_code = """\
import fetch from 'node-fetch';

const payload = %(json)s;

async function gooeyAPI() {
  const response = await fetch("%(api_url)s", {
    method: "POST",
    headers: {
        "Authorization": "%(auth_keyword)s " + process.env["GOOEY_API_KEY"],
        "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  const result = await response.json();
  console.log(response.status, result);
}

gooeyAPI();
            """ % dict(
                api_url=api_url,
                auth_keyword=auth_keyword,
                json=json.dumps(request_body, indent=2),
            )

        st.write(
            r"""
1. Generate an api key [below👇](#api-keys)

2. Install [node-fetch](https://www.npmjs.com/package/node-fetch) & add the `GOOEY_API_KEY` to your environment variables.  
Never store the api key [in your code](https://12factor.net/config) and don't use direcly in the browser.          
```bash
$ npm install node-fetch
$ export GOOEY_API_KEY=sk-xxxx
```

3. Use this sample code to call the API.    
If you encounter any issues, write to us at support@gooey.ai and make sure to include the full code snippet and the error message.
```js
%s
```
            """
            % js_code
        )

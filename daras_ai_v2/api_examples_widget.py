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


def api_example_generator(
    *, api_url: furl, request_body: dict, as_form_data: bool, as_async: bool
):
    js, python, curl = st.tabs(["`node.js`", "`python`", "`curl`"])

    filenames = []
    if as_async:
        api_url /= "async/"
    if as_form_data:
        filenames = list(get_filenames(request_body))
        for key, _ in filenames:
            request_body.pop(key, None)
        api_url /= "form/"
    api_url = str(api_url)
    if as_async:
        api_url = api_url.replace("v2", "v3")

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
        if as_async:
            curl_code = r"""
status_url=$(
%(curl_code)s | jq -r '.status_url'
)

while true; do
    result=$(curl $status_url -H "Authorization: %(auth_keyword)s $GOOEY_API_KEY")
    status=$(echo $result | jq -r '.status')
    if [ "$status" = "completed" ]; then
        echo $result
        break
    elif [ "$status" = "failed" ]; then
        echo $result
        break
    fi
    sleep 3
done
            """ % dict(
                curl_code=indent(curl_code.strip(), " " * 2),
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
assert response.ok, response.content
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
assert response.ok, response.content
            """ % dict(
                api_url=api_url,
                auth_keyword=auth_keyword,
                json=repr(request_body),
            )
        if as_async:
            py_code += r"""
from time import sleep            
            
status_url = response.headers["Location"]
while True:
    response = requests.get(status_url, headers={"Authorization": "%(auth_keyword)s " + os.environ["GOOEY_API_KEY"]})
    assert response.ok, response.content
    result = response.json()
    if result["status"] == "completed":
        print(response.status_code, result)
        break
    elif result["status"] == "failed":
        print(response.status_code, result)
        break
    else:
        sleep(3)
            """ % dict(
                api_url=api_url,
                auth_keyword=auth_keyword,
            )
        else:
            py_code += r"""
result = response.json()
print(response.status_code, result)
"""
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
            """ % dict(
                api_url=api_url,
                auth_keyword=auth_keyword,
                json=json.dumps(request_body, indent=2),
            )

        js_code += """
  if (!response.ok) {
    throw new Error(response.status);
  }
        """

        if as_async:
            js_code += """
  const status_url = response.headers.get("Location");
  while (true) {
    const response = await fetch(status_url, {
        method: "GET",
        headers: {
          "Authorization": "%(auth_keyword)s " + process.env["GOOEY_API_KEY"],
        },
    });
    if (!response.ok) {
        throw new Error(response.status);
    }
    
    const result = await response.json();
    if (result.status === "completed") {
        console.log(response.status, result);
        break;
    } else if (result.status === "failed") {
        console.log(response.status, result);
        break;
    } else {
        await new Promise(resolve => setTimeout(resolve, 3000));
    }
  }""" % dict(
                api_url=api_url,
                auth_keyword=auth_keyword,
            )
        else:
            js_code += """
  const result = await response.json();
  console.log(response.status, result);"""

        js_code += "\n}\n\ngooeyAPI();"

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

import json
import shlex
import threading
from textwrap import indent

from furl import furl

import gooey_gui as gui
from auth.token_authentication import auth_scheme
from daras_ai_v2 import settings
from daras_ai_v2.doc_search_settings_widgets import is_user_uploaded_url


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


# because black is not thread-safe
black_import_lock = threading.Lock()


def api_example_generator(
    *, api_url: furl, request_body: dict, as_form_data: bool, as_async: bool
):
    js, python, curl = gui.tabs(["`node.js`", "`python`", "`curl`"])

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
  -H "Authorization: %(auth_scheme)s $GOOEY_API_KEY" \
  %(files)s \
  -F json=%(json)s
                """ % dict(
                api_url=shlex.quote(api_url),
                auth_scheme=auth_scheme,
                files=" \\\n  ".join(
                    f"-F {key}=@{shlex.quote(filename)}" for key, filename in filenames
                ),
                json=shlex.quote(json.dumps(request_body, indent=2)),
            )
        else:
            curl_code = r"""
curl %(api_url)s \
  -H "Authorization: %(auth_scheme)s $GOOEY_API_KEY" \
  -H 'Content-Type: application/json' \
  -d %(json)s
            """ % dict(
                api_url=shlex.quote(api_url),
                auth_scheme=auth_scheme,
                json=shlex.quote(json.dumps(request_body, indent=2)),
            )
        if as_async:
            curl_code = r"""
status_url=$(
%(curl_code)s | jq -r '.status_url'
)

while true; do
    result=$(curl $status_url -H "Authorization: %(auth_scheme)s $GOOEY_API_KEY")
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
                auth_scheme=auth_scheme,
                json=shlex.quote(json.dumps(request_body, indent=2)),
            )

        gui.write(
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
            % curl_code.strip(),
            unsafe_allow_html=True,
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
        "Authorization": "%(auth_scheme)s " + os.environ["GOOEY_API_KEY"],
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
                auth_scheme=auth_scheme,
            )
        else:
            py_code = r"""
import os
import requests

payload = %(json)s

response = requests.post(
    "%(api_url)s",
    headers={
        "Authorization": "%(auth_scheme)s " + os.environ["GOOEY_API_KEY"],
    },
    json=payload,
)
assert response.ok, response.content
            """ % dict(
                api_url=api_url,
                auth_scheme=auth_scheme,
                json=repr(request_body),
            )
        if as_async:
            py_code += r"""
from time import sleep

status_url = response.headers["Location"]
while True:
    response = requests.get(status_url, headers={"Authorization": "%(auth_scheme)s " + os.environ["GOOEY_API_KEY"]})
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
                auth_scheme=auth_scheme,
            )
        else:
            py_code += r"""
result = response.json()
print(response.status_code, result)
"""
        with black_import_lock:
            from black import format_str
            from black.mode import Mode

        py_code = format_str(py_code, mode=Mode())
        gui.write(
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
            % py_code,
            unsafe_allow_html=True,
        )

    with js:
        if as_form_data:
            js_code = """\
import fetch, { FormData, fileFrom } from 'node-fetch';

const payload = %(json)s;

async function gooeyAPI() {
  const formData = new FormData();
  formData.set('json', JSON.stringify(payload));
%(files)s

  const response = await fetch("%(api_url)s", {
    method: "POST",
    headers: {
      "Authorization": "%(auth_scheme)s " + process.env["GOOEY_API_KEY"],
    },
    body: formData,
  });
            """ % dict(
                json=json.dumps(request_body, indent=2),
                files=indent(
                    "\n".join(
                        "formData.append(%r, await fileFrom(%r));" % (key, name)
                        for key, name in filenames
                    ),
                    " " * 2,
                ),
                api_url=api_url,
                auth_scheme=auth_scheme,
            )

        else:
            js_code = """\
import fetch from 'node-fetch';

const payload = %(json)s;

async function gooeyAPI() {
  const response = await fetch("%(api_url)s", {
    method: "POST",
    headers: {
      "Authorization": "%(auth_scheme)s " + process.env["GOOEY_API_KEY"],
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
            """ % dict(
                api_url=api_url,
                auth_scheme=auth_scheme,
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
          "Authorization": "%(auth_scheme)s " + process.env["GOOEY_API_KEY"],
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
                auth_scheme=auth_scheme,
            )
        else:
            js_code += """
  const result = await response.json();
  console.log(response.status, result);"""

        js_code += "\n}\n\ngooeyAPI();"

        gui.write(
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
            % js_code,
            unsafe_allow_html=True,
        )


def bot_api_example_generator(integration_id: str):
    from routers import bots_api
    from recipes.VideoBots import VideoBotsPage

    js_code = """
// create a stream on the server
let response = await fetch("%(api_url)s", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
  },
  body: JSON.stringify({
    // your integration's ID as shown in the Gooey.AI Integrations tab
    "integration_id": "%(integration_id)s",
    // the input text for the bot
    "input_prompt": "Hello, world!",
  }),
});
// get the server-sent events URL
let sseUrl = response.headers.get("Location");
console.log(sseUrl);

// clear screen
document.body.innerHTML = "";

// start listening to the stream
const evtSource = new EventSource(sseUrl);
// handle the stream events
evtSource.onmessage = (event) => {
    // display the message in the browser
    document.body.innerHTML += event.data + "<br><br>";
    // parse the message as JSON
    let data = JSON.parse(event.data);
    // log the message to the console
    console.log(data.type, data);
    // check if the message is the final response
    if (data.type === "final_response") {
        // close the stream
        evtSource.close();
    }
};
evtSource.onerror = (event) => {
    // log the error to the console
    console.error(event.data);
    // close the stream
    evtSource.close();
}
    """ % dict(
        api_url=(
            furl(settings.API_BASE_URL)
            / bots_api.app.url_path_for(bots_api.stream_create.__name__)
        ),
        integration_id=integration_id,
    )

    gui.write(
        f"""
Your Integration ID: `{integration_id}`


Use the following code snippet to stream messages from the bot.   
Note that you do not need the API key for this endpoint and can use it directly in the browser.

```js
{js_code.strip()}
```
        """,
        unsafe_allow_html=True,
    )

    api_docs_url = (
        furl(
            settings.API_BASE_URL,
            fragment_path=f"operation/{VideoBotsPage.slug_versions[0]}__stream_create",
        )
        / "docs"
    )
    gui.markdown(
        f"""
Read our <a href="{api_docs_url}" target="_blank">complete API</a> for features like conversation history, input media files, and more.
        """,
        unsafe_allow_html=True,
    )

    gui.js(
        """
document.startStreaming = async function() {
    document.getElementById('stream-output').style.display = 'flex';
    %s
}
        """
        % js_code.replace(
            "document.body", "document.getElementById('stream-output')"
        ).strip()
    )

    gui.html(
        f"""
<br>
<button class="btn btn-theme btn-secondary" onclick="document.startStreaming()">🏃‍♀️ Preview Streaming</button>
<pre style="text-align: left; background: #f5f2f0; display: none; flex-direction: column-reverse;" id="stream-output"></pre>
        """
    )

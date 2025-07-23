try:
    main = globals()["main"]
except KeyError:
    exit(0)

import json
import uuid
import io
from pathlib import Path
from urllib.parse import urljoin

with open("/app/input.json") as f:
    variables, prefix_url, output_limit = json.load(f)

ret = main(**variables)


def json_encoder(obj):
    if isinstance(obj, io.RawIOBase):
        obj = obj.readall()
    elif isinstance(obj, io.BufferedIOBase):
        obj = obj.read()
    elif isinstance(obj, io.TextIOBase):
        obj = obj.read().encode()

    if isinstance(obj, bytes):
        path = Path(f"/workspace/unnamed/{uuid.uuid4()}.bin")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(obj)
        obj = path

    if isinstance(obj, Path):
        filename = str(obj.resolve().relative_to("/workspace"))
        return urljoin(prefix_url, filename)

    raise TypeError(
        f"Return value must be JSON serializable. Cannot serialize object of {type(obj)}"
    )


with open("/app/return_value.json", "wb") as f:
    ret_json = json.dumps(ret, default=json_encoder).encode()
    if len(ret_json) > output_limit:
        raise ValueError(
            f"Return value is too large, must be less than {output_limit} bytes."
        )
    f.write(ret_json)

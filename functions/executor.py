try:
    main = globals()["main"]
except KeyError:
    exit(0)

import json
import sys
import uuid
import io
from pathlib import Path
from urllib.parse import urljoin


def json_encoder(obj):
    if isinstance(obj, io.RawIOBase):
        obj = obj.readall()
    elif isinstance(obj, io.BufferedIOBase):
        obj = obj.read()
    elif isinstance(obj, io.TextIOBase):
        obj = obj.read().encode()

    if isinstance(obj, bytes):
        path = Path(f"/workspace/unnamed/{uuid.uuid4()}.bin")
        path.write_bytes(obj)
        obj = path

    if isinstance(obj, Path):
        filename = str(obj.resolve().relative_to("/workspace"))
        return urljoin(prefix_url, filename)

    raise TypeError(
        f"Return value must be JSON serializable. Cannot serialize object of {type(obj)}"
    )


kwargs_json = sys.argv[1]
prefix_url = sys.argv[2]

kwargs = json.loads(kwargs_json)
ret = main(**kwargs)

with open("/output/return_value.json", "wb") as f:
    ret_json = json.dumps(ret, default=json_encoder).encode()
    if len(ret_json) > 256_000:
        raise ValueError("Return value is too large, must be less than 256KB.")
    f.write(ret_json)

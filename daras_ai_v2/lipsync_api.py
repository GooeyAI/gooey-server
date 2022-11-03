import base64

import requests


def wav2lip(*, face: str, audio: str, pads: (int, int, int, int)) -> bytes:
    r = requests.post(
        "http://35.225.120.135:5001/predictions",
        json={
            "input": {
                "face": face,
                "audio": audio,
                "pads": " ".join(map(str, pads)),
                # "out_height": 480,
                # "smooth": True,
                # "fps": 25,
            },
        },
    )
    r.raise_for_status()

    b64_data = r.json()["output"]
    b64_data = b64_data[b64_data.find(",") + 1 :]
    return base64.b64decode(b64_data)

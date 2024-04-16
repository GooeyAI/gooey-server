from daras_ai.image_input import upload_file_from_bytes


def run():
    with open("fixture.json") as f:
        data = f.read().encode()

    print(
        upload_file_from_bytes(
            filename="fixture.json", data=data, content_type="application/json"
        )
    )

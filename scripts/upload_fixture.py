from firebase_admin import storage

from daras_ai_v2 import settings


def run():
    with open("fixture.json") as f:
        data = f.read().encode()

    bucket = storage.bucket(settings.GS_BUCKET_NAME)
    blob = bucket.blob(
        "dara-c1b52.appspot.com/daras_ai/media/ca0f13b8-d6ed-11ee-870b-8e93953183bb/fixture.json"
    )

    blob.upload_from_string(data, content_type="application/json")

    print("Uploaded fixture.json to", blob.public_url)

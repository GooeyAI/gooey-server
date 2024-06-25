import pytest

from daras_ai.image_input import storage_blob_for
from daras_ai_v2 import settings
from daras_ai_v2.crypto import get_random_doc_id
from glossary_resources.models import GlossaryResource
from tests.test_translation import _test_run_google_translate_one

GLOSSARY = [
    {
        "en-US": "Gooey.AI",
        "hi-IN": "गुई ए आई",
        "pos": "noun",
        "description": "Translation of Gooey.AI from Hindi to English",
        "random": "random",
    },
    {
        "en-US": "Gooey.AI",
        "hi-IN": "गुई डॉट ए आई",
        "pos": "noun",
        "description": "Translation of Gooey.AI from Hindi to English",
        "random": get_random_doc_id(),
    },
    {
        "en-US": "agniastra",
        "hi-IN": "अग्निअस्त्र",
        "pos": "noun",
        "description": "well labs agniastra",
    },
]

TRANSLATION_TESTS_GLOSSARY = [
    (
        "एक एकड़ भूमि के लिए कितनी अग्निअस्त्र की आवश्यकता होती है",
        "how many fire extinguishers are required for one acre of land",  # default
        "how many agniastra are required for one acre of land",  # using glossary
    ),
    (
        "गुई डॉट ए आई से हम क्या कर सकते हैं",
        "What can we do with Gui.AI",
        "What can we do with Gooey.AI",
    ),
    (
        "गुई ए आई से हम क्या कर सकते हैं",
        "What can we do with AI",
        "What can we do with Gooey.AI",
    ),
]


@pytest.fixture
def glossary_url():
    import pandas as pd

    df = pd.DataFrame.from_records(GLOSSARY)
    blob = storage_blob_for("test glossary.csv")
    blob.upload_from_string(df.to_csv(index=False).encode(), content_type="text/csv")

    try:
        yield blob.public_url
    finally:
        blob.delete()
        GlossaryResource.objects.all().delete()


@pytest.mark.skipif(not settings.GS_BUCKET_NAME, reason="No GCS bucket")
@pytest.mark.django_db
def test_run_google_translate_glossary(glossary_url, threadpool_subtest):
    for text, expected, expected_with_glossary in TRANSLATION_TESTS_GLOSSARY:
        threadpool_subtest(
            _test_run_google_translate_one,
            text,
            expected,
        )
        threadpool_subtest(
            _test_run_google_translate_one,
            text,
            expected_with_glossary,
            glossary_url=glossary_url,
        )

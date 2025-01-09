import pytest

from conftest import flaky
from daras_ai_v2.asr import run_google_translate

TRANSLATION_TESTS = [
    # hindi romanized
    (
        "hi",
        "Hi Sir Mera khet me mircha ke ped me fal gal Kar gir hai to  iske liye  ham kon sa dawa  de please  help me",
        "hi sir the fruits on the chilli tree in my field have fallen down what medicine should i give you? please help me",
    ),
    (
        "hi",
        "Mirchi ka ped",
        "chilli tree",
    ),
    # telugu
    (
        "te",
        "90 రోజుల తర్వాత మిర్చి తోటలో ఏమేమి పోషకాలు వేసి వేయాలి",
        "what nutrients should be added to the chilli garden after 90 days?",
    ),
    # swahili
    (
        "sw",
        "Unastahili kuchanganya mchanga na nini unapopanda kahawa?",
        "what should you mix the soil with when planting coffee?",
    ),
    # amharic
    (
        "am",
        "ለዘር የሚሆን የስንዴ ምርጥ ዘር ዓይነት ስንት ናቸው?እንደ ሀገረችን እትዮጵያ ደረጃ?",
        "what are the best wheat seeds for seed production? according to the standards of our country ethiopia?",
    ),
    # spanish
    (
        "es",
        "hola senor me gusta el chile",
        "hello sir, i like chili",
    ),
    # english
    (
        "en",
        "what is the best type of wheat for seed?",
        "what is the best type of wheat for seed?",
    ),
]


@pytest.mark.skip(
    reason="Translation tests temporarily disabled due to frequent false positives"
)
def test_google_translate(threadpool_subtest):
    for lang, text, expected in TRANSLATION_TESTS:
        threadpool_subtest(google_translate_check, text, expected, source_language=lang)


@flaky
def google_translate_check(
    text: str,
    expected: str,
    *,
    glossary_url: str = None,
    target_language: str = "en",
    source_language: str = None
):
    actual = run_google_translate(
        texts=[text],
        target_language=target_language,
        source_language=source_language,
        glossary_url=glossary_url,
    )[0]
    actual_norm = actual.replace(".", "").replace(",", "").strip().lower()
    expected_norm = expected.replace(".", "").replace(",", "").strip().lower()
    assert actual_norm == expected_norm

from conftest import flaky
from daras_ai_v2.asr import run_google_translate


TRANSLATION_TESTS = [
    # hindi romanized
    (
        "hi",
        "Hi Sir Mera khet me mircha ke ped me fal gal Kar gir hai to  iske liye  ham kon sa dawa  de please  help me",
        "hi sir in my field the fruits of chilli tree are rotting and falling so which medicine should i give for this please help",
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
        "after 90 days what nutrients should be added to the pepper garden?",
    ),
    # swahili
    (
        "sw",
        "Unastahili kuchanganya mchanga na nini unapopanda kahawa?",
        "What should you mix sand with when planting coffee?",
    ),
    # amharic
    (
        "am",
        "ለዘር የሚሆን የስንዴ ምርጥ ዘር ዓይነት ስንት ናቸው?እንደ ሀገረችን እትዮጵያ ደረጃ?",
        "What are the best types of wheat for seed? According to our country, Ethiopia?",
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

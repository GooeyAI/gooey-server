import pytest

from daras_ai_v2.asr import run_google_translate

TRANSLATION_TESTS = [
    # hindi romanized
    (
        "Hi Sir Mera khet me mircha ke ped me fal gal Kar gir hai to  iske liye  ham kon sa dawa  de please  help me",
        "Hi sir the fruits of chilli tree in my field have rotted and fallen so what medicine should we give for this please help",
    ),
    (
        "Mirchi ka ped",
        "chili tree",
    ),
    # hindi
    (
        "ान का नर्सरी खेत में रोकने के लिए कितने दिन में तैयार हो जाता है",
        "in how many days the corn nursery is ready to stop in the field",
    ),
    # telugu
    (
        "90 రోజుల తర్వాత మిర్చి తోటలో ఏమేమి పోషకాలు వేసి వేయాలి",
        "after 90 days what nutrients should be added to the pepper garden?",
    ),
    # swahili
    (
        "Unastahili kuchanganya mchanga na nini unapopanda kahawa?",
        "What should you mix sand with when planting coffee?",
    ),
    # amharic
    (
        "ለዘር የሚሆን የስንዴ ምርጥ ዘር ዓይነት ስንት ናቸው?እንደ ሀገረችን እትዮጵያ ደረጃ?",
        "What are the best types of wheat for seed? According to our country, Ethiopia?",
    ),
    # english
    (
        "what is the best type of wheat for seed?",
        "what is the best type of wheat for seed?",
    ),
    (
        "hola senor me gusta el chile",
        "hello sir, i like chili",
    ),
]


@pytest.mark.parametrize("text, expected", TRANSLATION_TESTS)
def test_run_google_translate(text: str, expected: str):
    actual = run_google_translate([text], "en")[0]
    assert (
        actual.replace(".", "").replace(",", "").strip().lower()
        == expected.replace(".", "").replace(",", "").strip().lower()
    )

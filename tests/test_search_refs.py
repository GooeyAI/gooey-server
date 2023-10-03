import pytest

from daras_ai_v2.search_ref import parse_refs, generate_footnote_symbol


def test_ref_parser():
    text = "This is a [1, 2, 3]. test. [4, 5] [6] [7, 8, 9]"
    references = [
        {
            "url": "https://example.com/1",
            "title": "Example 1",
            "snippet": "Example 1",
            "score": 1.0,
        },
        {
            "url": "https://example.com/2",
            "title": "Example 2",
            "snippet": "Example 2",
            "score": 1.0,
        },
        {
            "url": "https://example.com/3",
            "title": "Example 3",
            "snippet": "Example 3",
            "score": 1.0,
        },
        {
            "url": "https://example.com/4",
            "title": "Example 4",
            "snippet": "Example 4",
            "score": 1.0,
        },
        {
            "url": "https://example.com/5",
            "title": "Example 5",
            "snippet": "Example 5",
            "score": 1.0,
        },
        {
            "url": "https://example.com/6",
            "title": "Example 6",
            "snippet": "Example 6",
            "score": 1.0,
        },
        {
            "url": "https://example.com/7",
            "title": "Example 7",
            "snippet": "Example 7",
            "score": 1.0,
        },
        {
            "url": "https://example.com/8",
            "title": "Example 8",
            "snippet": "Example 8",
            "score": 1.0,
        },
        {
            "url": "https://example.com/9",
            "title": "Example 9",
            "snippet": "Example 9",
            "score": 1.0,
        },
    ]

    assert list(parse_refs(text, references)) == [
        (
            "This is a",
            {
                1: {
                    "url": "https://example.com/1",
                    "title": "Example 1",
                    "snippet": "Example 1",
                    "score": 1.0,
                },
                2: {
                    "url": "https://example.com/2",
                    "title": "Example 2",
                    "snippet": "Example 2",
                    "score": 1.0,
                },
                3: {
                    "url": "https://example.com/3",
                    "title": "Example 3",
                    "snippet": "Example 3",
                    "score": 1.0,
                },
            },
        ),
        (
            ". test.",
            {
                4: {
                    "url": "https://example.com/4",
                    "title": "Example 4",
                    "snippet": "Example 4",
                    "score": 1.0,
                },
                5: {
                    "url": "https://example.com/5",
                    "title": "Example 5",
                    "snippet": "Example 5",
                    "score": 1.0,
                },
                6: {
                    "url": "https://example.com/6",
                    "title": "Example 6",
                    "snippet": "Example 6",
                    "score": 1.0,
                },
                7: {
                    "url": "https://example.com/7",
                    "title": "Example 7",
                    "snippet": "Example 7",
                    "score": 1.0,
                },
                8: {
                    "url": "https://example.com/8",
                    "title": "Example 8",
                    "snippet": "Example 8",
                    "score": 1.0,
                },
                9: {
                    "url": "https://example.com/9",
                    "title": "Example 9",
                    "snippet": "Example 9",
                    "score": 1.0,
                },
            },
        ),
    ]


def test_generate_footnote_symbol():
    assert generate_footnote_symbol(0) == "*"
    assert generate_footnote_symbol(1) == "†"
    assert generate_footnote_symbol(13) == "✡"
    assert generate_footnote_symbol(14) == "**"
    assert generate_footnote_symbol(15) == "††"
    assert generate_footnote_symbol(27) == "✡✡"
    assert generate_footnote_symbol(28) == "***"
    assert generate_footnote_symbol(29) == "†††"
    assert generate_footnote_symbol(41) == "✡✡✡"
    assert generate_footnote_symbol(70) == "******"
    assert generate_footnote_symbol(71) == "††††††"

    # testing with non-integer index
    with pytest.raises(TypeError):
        generate_footnote_symbol(1.5)

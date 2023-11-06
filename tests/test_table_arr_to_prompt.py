import pytest

from daras_ai_v2.azure_doc_extract import _remove_long_dupe_header

TESTS = [
    (
        ["", "", ""],
        ["", "", ""],
    ),
    (
        ["", "", "a"],
        ["", "", "a"],
    ),
    (
        ["a", "a", "a"],
        ["a", "", ""],
    ),
    (
        ["a", "b", "c"],
        ["a", "b", "c"],
    ),
    (
        ["a", "b", "b"],
        ["a", "b", "b"],
    ),
    (
        ["a", "b", "b", "b"],
        ["a", "b", "", ""],
    ),
    (
        ["a", "b", "b", "c", "c"],
        ["a", "b", "b", "c", "c"],
    ),
    (
        ["a", "b", "b", "c", "c", "c"],
        ["a", "b", "b", "c", "", ""],
    ),
    (
        ["a", "b", "b", "c", "c", "c", ""],
        ["a", "b", "b", "c", "", "", ""],
    ),
    (
        ["a", "b", "b", "d", "c", ""],
        ["a", "b", "b", "d", "c", ""],
    ),
    (
        ["a", "b", "c", "", "", "", ""],
        ["a", "b", "c", "", "", "", ""],
    ),
]


@pytest.mark.parametrize("row, expected", TESTS)
def test_remove_long_dupe_header(row, expected):
    assert _remove_long_dupe_header(row) == expected

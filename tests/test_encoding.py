from daras_ai_v2.csv_lines import unicode_unescape, csv_encode_row, csv_decode_row


def test_unicode_escape():
    # Case 1: Normal text (should remain unchanged)
    assert unicode_unescape("Hello World") == "Hello World"

    # Case 2: Hex escape (\xXX)
    assert unicode_unescape("Euro symbol: \\xAC") == "Euro symbol: ¬"

    # Case 3: Unicode escapes
    assert unicode_unescape("Euro symbol: \\u20AC") == "Euro symbol: €"
    assert unicode_unescape("Face: \\U0001F600") == "Face: 😀"

    # Case 4: Mixed escapes
    assert unicode_unescape("Combo: \\xAC \\u00A9 \\U0001F680") == "Combo: ¬ © 🚀"

    # Case 5: Invalid escapes (should remain unchanged)
    assert unicode_unescape("Broken \\xGZ") == "Broken \\xGZ"
    assert unicode_unescape("Broken \\uXYZZ") == "Broken \\uXYZZ"

    # Case 6: String already containing Unicode characters (should remain unchanged)
    assert unicode_unescape("Hello 😊") == "Hello 😊"

    # Case 7: Previously failing test
    assert unicode_unescape(r"a \u20ac") == "a €"


def test_csv_encode_decode():
    assert csv_decode_row(csv_encode_row("Hello World"))[0] == "Hello World"
    assert csv_decode_row(csv_encode_row("Euro symbol: ¬"))[0] == "Euro symbol: ¬"
    assert csv_decode_row(csv_encode_row("Euro symbol: €"))[0] == "Euro symbol: €"
    assert csv_decode_row(csv_encode_row("Face: 😀"))[0] == "Face: 😀"
    assert csv_decode_row(csv_encode_row("Combo: ¬ © 🚀"))[0] == "Combo: ¬ © 🚀"
    assert csv_decode_row(csv_encode_row("Broken \\xGZ"))[0] == r"Broken \\xGZ"
    assert csv_decode_row(csv_encode_row("Broken \\uXYZZ"))[0] == r"Broken \\uXYZZ"
    assert csv_decode_row(csv_encode_row("Hello 😊"))[0] == "Hello 😊"
    assert csv_decode_row(csv_encode_row("a €"))[0] == "a €"

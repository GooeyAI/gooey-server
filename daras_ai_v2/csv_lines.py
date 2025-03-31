import csv
import re
from io import StringIO


def csv_encode_row(*csv_row) -> str:
    """
    Converts a Python list to a CSV-encoded string.
    """
    output = StringIO()
    writer = csv.writer(output)
    csv_row = [str(x) for x in csv_row if x is not None]
    writer.writerow(csv_row)
    csv_text = output.getvalue().strip()  # Strip to remove trailing newline
    csv_text = unicode_escape(csv_text)
    return csv_text


def csv_decode_row(csv_text: str) -> list[str]:
    """
    Converts a CSV-encoded string to a Python list.
    """
    # Check if the string is unicode-escaped
    csv_text = unicode_unescape(csv_text)
    input_stream = StringIO(csv_text)
    reader = csv.reader(input_stream)
    return next(reader)


def unicode_escape(text: str) -> str:
    """
    Escapes special characters in a string.
    """
    return text.encode("unicode_escape").decode()


# Detects Unicode escape sequences - https://docs.python.org/3/howto/unicode.html#unicode-literals-in-python-source-code
unicode_escape_pat = re.compile(
    r"(\\x[0-9a-fA-F]{2})|"  # Matches \xXX (hex escape)
    r"(\\u[0-9a-fA-F]{4})|"  # Matches \uXXXX (16-bit Unicode)
    r"(\\U[0-9a-fA-F]{8})"  # Matches \UXXXXXXXX (32-bit Unicode)
)


def unicode_unescape(text: str) -> str:
    """
    Unescapes special characters in a string.
    """
    # this check is necessary to avoid decoding non-unicode-esacped strings
    if unicode_escape_pat.search(text):
        try:
            text = text.encode().decode("unicode_escape")
        except UnicodeDecodeError:
            pass
    return text

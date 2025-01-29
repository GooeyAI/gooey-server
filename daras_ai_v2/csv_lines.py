import csv
from io import StringIO


def csv_encode_row(*csv_row) -> str:
    """
    Converts a Python list to a CSV-encoded string.
    """
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(map(str, csv_row))
    return output.getvalue().strip()  # Strip to remove trailing newline


def csv_decode_row(csv_text: str) -> list[str]:
    """
    Converts a CSV-encoded string to a Python list.
    """
    input_stream = StringIO(csv_text)
    reader = csv.reader(input_stream)
    return next(reader)

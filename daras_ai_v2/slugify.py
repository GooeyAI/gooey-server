import re


def slugify(s: str) -> str:
    # remove leading/trailing space, and make lowercase
    s = s.strip().lower()
    # remove multiple space
    s = re.sub(r"\s+", " ", s)
    # replace non-alphanumeric chars (and space) with "-"
    s = re.sub(r"[^a-z0-9]+", " ", s)
    # grab upto first 5 words
    s = "-".join(s.split()[:5])

    return s

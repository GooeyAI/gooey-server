import re

import phonenumbers

EXTENSION_NUMBER_LENGTH = 5


REGIONAL_INDICATOR_A = ord("🇦")  # U+1F1E6
ASCII_A = ord("A")


def country_code_label(country_code: str) -> str:
    """Derive a display label from an ISO 3166-1 alpha-2 country code.

    e.g. "US" → "🇺🇸 US +1", "IN" → "🇮🇳 IN +91"
    """
    cc = country_code.upper()
    flag = "".join(chr(REGIONAL_INDICATOR_A + (ord(ch) - ASCII_A)) for ch in cc)
    dial_code = phonenumbers.country_code_for_region(cc)
    if not dial_code:
        return f"{flag} {cc}"
    return f"{flag} {cc} +{dial_code}"


def parse_extension_number(message_text: str) -> int | None:
    if not message_text:
        return None
    match = re.search(r"\b(\d{%d})\b" % EXTENSION_NUMBER_LENGTH, message_text)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    else:
        return None

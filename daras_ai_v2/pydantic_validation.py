import typing

from pydantic import HttpUrl

if typing.TYPE_CHECKING:
    from pydantic.error_wrappers import ErrorDict


class FieldHttpUrl(HttpUrl):
    min_length = 0  # allow empty string


CUSTOM_MESSAGES = {
    "value_error.url": (
        "{original_msg}. "
        "Please make sure the URL is correct and accessible. "
        "If you are trying to use a local file, please use the [Upload Files via Form Data] option on https://gooey.ai/api/ to upload the file directly."
    ),
}


def convert_errors(errors: list["ErrorDict"]):
    for error in errors:
        for type_prefix, custom_message in CUSTOM_MESSAGES.items():
            if not error["type"].startswith(type_prefix):
                continue
            ctx = error.get("ctx", {})
            custom_message = custom_message.format(**ctx, original_msg=error["msg"])
            error["msg"] = custom_message

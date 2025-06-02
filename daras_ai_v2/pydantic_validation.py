import typing

from pydantic import HttpUrl, WrapValidator, ValidatorFunctionWrapHandler

if typing.TYPE_CHECKING:
    from pydantic_core import ErrorDetails


def allow_empty_or_url(
    url: str, handler: ValidatorFunctionWrapHandler
) -> HttpUrl | None:
    if url == "":
        url = None
    return handler(url)


OptionalHttpUrl = typing.Annotated[HttpUrl | None, WrapValidator(allow_empty_or_url)]


CUSTOM_MESSAGES = {
    "value_error.url": (
        "{original_msg}. "
        "Please make sure the URL is correct and accessible. "
        "If you are trying to use a local file, please use the [Upload Files via Form Data] option on https://gooey.ai/api/ to upload the file directly."
    ),
}


def convert_errors(errors: typing.Iterable["ErrorDetails"]):
    for error in errors:
        for type_prefix, custom_message in CUSTOM_MESSAGES.items():
            if not error["type"].startswith(type_prefix):
                continue
            ctx = error.get("ctx", {})
            custom_message = custom_message.format(**ctx, original_msg=error["msg"])
            error["msg"] = custom_message

import typing

import django.core.exceptions
import pydantic
from django.core.validators import URLValidator
from pydantic import GetJsonSchemaHandler, GetCoreSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import core_schema, PydanticCustomError


class PydanticEnumMixin:
    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: typing.Any, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        def validate_enum(name: str) -> cls:
            try:
                return cls[name]
            except KeyError:
                raise PydanticCustomError(
                    "enum", f"Input should be one of {set(cls.__members__.keys())}"
                )

        return core_schema.no_info_before_validator_function(
            validate_enum,
            core_schema.enum_schema(cls, list(cls.__members__.values())),
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda x: x.name
            ),
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls, _core_schema: core_schema.CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        return dict(enum=[m.name for m in cls])


class HttpUrlTypeAnnotation:
    @classmethod
    def __get_pydantic_json_schema__(
        cls, _core_schema: core_schema.CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        return handler(core_schema.url_schema(allowed_schemes=["http", "https"]))


def validate_url_or_none(url: str | None) -> str | None:
    if not url:
        return None
    return validate_url(url)


def validate_url(url: str) -> str:
    try:
        URLValidator(schemes=["http", "https"])(url)
    except django.core.exceptions.ValidationError as e:
        raise PydanticCustomError(
            "url_parsing",
            f"{e.message} If you are trying to use a local file, please use the [Upload Files via Form Data] option on https://gooey.ai/api/ to upload the file directly.",
        )
    return url


HttpUrlStr = typing.Annotated[
    str,
    pydantic.AfterValidator(validate_url),
    HttpUrlTypeAnnotation,
]
OptionalHttpUrlStr = typing.Annotated[
    str | None,
    pydantic.AfterValidator(validate_url_or_none),
    HttpUrlTypeAnnotation,
]

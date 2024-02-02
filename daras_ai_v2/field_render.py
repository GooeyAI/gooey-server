import typing

from pydantic import BaseModel


def field_title_desc(model: typing.Type[BaseModel], name: str) -> str:
    field = model.__fields__[name]
    return "\n".join(
        filter(
            None,
            [field.field_info.title, field.field_info.description or ""],
        )
    )


def field_title(model: typing.Type[BaseModel], name: str) -> str:
    field = model.__fields__[name]
    return "\n".join(
        filter(
            None,
            [field.field_info.title],
        )
    )


def field_desc(model: typing.Type[BaseModel], name: str) -> str:
    field = model.__fields__[name]
    return "\n".join(
        filter(
            None,
            [field.field_info.description or ""],
        )
    )

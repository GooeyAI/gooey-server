import typing

from pydantic import BaseModel


def field_title_desc(model: typing.Type[BaseModel], name: str) -> str:
    return "\n".join(filter(None, [field_title(model, name), field_desc(model, name)]))


def field_title(model: typing.Type[BaseModel], name: str) -> str:
    field = model.__fields__[name]
    return field.field_info.title


def field_desc(model: typing.Type[BaseModel], name: str) -> str:
    field = model.__fields__[name]
    return field.field_info.description or ""

import typing

from pydantic import BaseModel


def field_label_val(model: BaseModel, attr: str) -> dict:
    return {
        "label": field_title_desc(model.__class__, attr),
        "value": getattr(model, attr),
    }


def field_title_desc(model: typing.Type[BaseModel], name: str) -> str:
    return "\n".join(filter(None, [field_title(model, name), field_desc(model, name)]))


def field_title(model: typing.Type[BaseModel], name: str) -> str:
    return model.model_fields[name].title or ""


def field_desc(model: typing.Type[BaseModel], name: str) -> str:
    return model.model_fields[name].description or ""

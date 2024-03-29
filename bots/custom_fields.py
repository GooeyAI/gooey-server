from typing import Any

import simplejson
from django.core.validators import URLValidator
from django.db import models


class CustomURLField(models.URLField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("max_length", 2048)
        super().__init__(*args, **kwargs)

    def clean(self, value, model_instance):
        if "://" not in value:
            value = "http://" + value
        return super().clean(value, model_instance)


class ValidatedURLField(models.URLField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("max_length", 2048)
        super().__init__(*args, **kwargs)

    def clean(self, value, model_instance):
        if "://" not in value:
            value = "http://" + value
        URLValidator(schemes=["http", "https"])(value)
        return super().clean(value, model_instance)


class StrippedTextField(models.TextField):
    def clean(self, value, model_instance):
        if value is not None:
            value = value.strip()
        return super().clean(value, model_instance)


class PostgresJSONEncoder(simplejson.JSONEncoder):
    """
    A JSONEncoder subclass that knows how to handle
    - this stupid postgres bug: https://stackoverflow.com/questions/31671634/handling-unicode-sequences-in-postgresql/31672314#31672314
    - handles NaN: https://stackoverflow.com/questions/28639953/python-json-encoder-convert-nans-to-null-instead
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.ignore_nan = True

    def encode(self, o):
        ret = super().encode(o)
        ret = ret.replace("\\u0000", "")
        return ret

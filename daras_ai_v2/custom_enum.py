import functools
import typing
from enum import Enum

import typing_extensions


def cached_classmethod(func: typing.Callable):
    """
    This cache is a hack to get around a bug where
    dynamic Enums with the same name cause a crash
    when generating the OpenAPI spec.
    """

    @functools.wraps(func)
    def wrapper(cls):
        if not hasattr(cls, "_cached_classmethod"):
            cls._cached_classmethod = {}
        if id(func) not in cls._cached_classmethod:
            cls._cached_classmethod[id(func)] = func(cls)

        return cls._cached_classmethod[id(func)]

    return wrapper


T = typing.TypeVar("T", bound="GooeyEnum")


class GooeyEnum(Enum):
    @property
    def api_value(self):
        # api_value is usually the name
        return self.name

    @classmethod
    def db_choices(cls):
        return [(e.db_value, e.label) for e in cls]

    @classmethod
    def from_db(cls, db_value) -> typing_extensions.Self:
        for e in cls:
            if e.db_value == db_value:
                return e
        raise ValueError(f"Invalid {cls.__name__} {db_value=}")

    @classmethod
    @property
    @cached_classmethod
    def api_enum(cls):
        """
        Enum that is useful as a type in API requests.

        Maps `api_value`->`api_value` (default: `name`->`name`)
        for all values.

        The title (same as the Enum class name) will be
        used as the new Enum's title. This will be passed
        on to the OpenAPI schema and the generated SDK.
        """
        return Enum(cls.__name__, {e.api_value: e.api_value for e in cls})

    @classmethod
    def from_api(cls, api_value: str) -> typing_extensions.Self:
        for e in cls:
            if e.api_value == api_value:
                return e
        raise ValueError(f"Invalid {cls.__name__} {api_value=}")

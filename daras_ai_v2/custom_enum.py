import typing
from enum import Enum

import typing_extensions

T = typing.TypeVar("T", bound="GooeyEnum")


class GooeyEnum(Enum):
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
    def api_choices(cls):
        return typing.Literal[tuple(e.name for e in cls)]

    @classmethod
    @property
    def api_enum(cls):
        """
        Enum that is useful as a type in API requests.

        Maps `name`->`name` for all values.
        The title (same as the Enum class name) will be
        used as the new Enum's title. This will be passed
        on to the OpenAPI schema and the generated SDK.
        """
        # this cache is a hack to get around a bug where
        # dynamic Enums with the same name crash when
        # generating the OpenAPI spec
        if not hasattr(cls, "_cached_api_enum"):
            cls._cached_api_enum = {}
        if cls.__name__ not in cls._cached_api_enum:
            cls._cached_api_enum[cls.__name__] = Enum(
                cls.__name__, {e.name: e.name for e in cls}
            )

        return cls._cached_api_enum[cls.__name__]

    @classmethod
    def from_api(cls, name: str) -> typing_extensions.Self:
        for e in cls:
            if e.name == name:
                return e
        raise ValueError(f"Invalid {cls.__name__} {name=}")

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
    def from_api(cls, name: str) -> typing_extensions.Self:
        for e in cls:
            if e.name == name:
                return e
        raise ValueError(f"Invalid {cls.__name__} {name=}")

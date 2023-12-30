from contextlib import contextmanager
from typing import Type


class UserError(Exception):
    pass


@contextmanager
def raise_as_user_error(excs: list[Type[Exception]]):
    try:
        yield
    except tuple(excs) as e:
        raise UserError(str(e)) from e

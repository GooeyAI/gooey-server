import typing

query_params: dict[str, str] = {}
session_state: dict[str, typing.Any] = {}


def get_query_params():
    return query_params

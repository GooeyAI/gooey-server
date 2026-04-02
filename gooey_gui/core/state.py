import threading
import typing


threadlocal = threading.local()


def get_session_state() -> dict[str, typing.Any]:
    try:
        return threadlocal.session_state
    except AttributeError:
        threadlocal.session_state = {}
        return threadlocal.session_state


def set_session_state(state: dict[str, typing.Any]):
    threadlocal.session_state = state


def get_query_params() -> dict[str, str]:
    try:
        return threadlocal.query_params
    except AttributeError:
        threadlocal.query_params = {}
        return threadlocal.query_params


def set_query_params(params: dict[str, str]):
    threadlocal.query_params = params

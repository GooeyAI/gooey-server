from .components import *
from .core import *


def __getattr__(name):
    if name == "session_state":
        return get_session_state()
    else:
        raise AttributeError(name)

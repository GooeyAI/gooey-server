import typing

from .exceptions import (
    RedirectException,
    QueryParamsRedirectException,
    StopException,
    RerunException,
    rerun,
    stop,
)
from .pubsub import (
    realtime_push,
    realtime_pull,
    realtime_subscribe,
    get_subscriptions,
    realtime_clear_subs,
    md5_values,
)
from .renderer import (
    RenderTreeNode,
    NestingCtx,
    renderer,
    route,
    current_root_ctx,
    add_styles,
)
from .state import (
    get_session_state,
    set_session_state,
    get_query_params,
    set_query_params,
)
from .state_interactions import use_state, run_in_thread, cache_in_session_state

session_state: dict[str, typing.Any]


def __getattr__(name):
    if name == "session_state":
        return get_session_state()
    else:
        raise AttributeError(name)

import datetime
from typing import Any

DEFAULT_DATE_OPTIONS = {
    "day": "numeric",
    "month": "short",
}
DEFAULT_TIME_OPTIONS = {
    "hour": "numeric",
    "hour12": True,
    "minute": "numeric",
}


def render_local_dt_attrs(
    dt: datetime.datetime | float,
    *,
    date_options: dict[str, Any] | None = None,
    time_options: dict[str, Any] | None = None,
):
    if isinstance(dt, datetime.datetime):
        dt = dt.timestamp()
    return {
        "renderLocalDt": dt * 1000,
        "renderLocalDtDateOptions": date_options or DEFAULT_DATE_OPTIONS,
        "renderLocalDtTimeOptions": time_options or DEFAULT_TIME_OPTIONS,
    }

import typing
from datetime import datetime, timedelta

from django.utils import timezone

T = typing.TypeVar("T")

THRESHOLDS = [
    (timedelta(days=365), "y"),
    (timedelta(days=30), "mo"),
    (timedelta(days=1), "d"),
    (timedelta(hours=1), "h"),
    (timedelta(minutes=1), "m"),
    (timedelta(seconds=3), "s"),
]


def get_relative_time(timestamp: datetime) -> str:
    diff = timezone.now() - timestamp

    if abs(diff) < timedelta(seconds=3):
        return "Just now"

    for threshold, unit in THRESHOLDS:
        if abs(diff) >= threshold:
            value = round(diff / threshold)
            return (
                f"{value}{unit} ago" if diff > timedelta() else f"in {abs(value)}{unit}"
            )

    return "Just now"


def clamp(x: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(x, max_value))

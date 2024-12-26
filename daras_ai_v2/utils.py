from django.utils import timezone
from datetime import timedelta, datetime

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
    for threshold, unit in THRESHOLDS:
        if diff >= threshold:
            return f"{round(diff / threshold)}{unit} ago"
    return "Just now"

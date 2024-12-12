from django.utils import timezone
from datetime import timedelta


def get_relative_time(timestamp):
    diff = timezone.now() - timestamp
    seconds = diff.total_seconds()

    if seconds < 2:
        return "Just now"
    if seconds < timedelta(minutes=1).total_seconds():
        return f"{int(seconds)}s ago"
    elif seconds < timedelta(hours=1).total_seconds():
        return f"{int(seconds/timedelta(minutes=1).total_seconds())}m ago"
    elif seconds < timedelta(days=1).total_seconds():
        return f"{int(seconds/timedelta(hours=1).total_seconds())}h ago"
    elif seconds < timedelta(days=30).total_seconds():
        return f"{int(seconds/timedelta(days=1).total_seconds())}d ago"
    elif seconds < timedelta(days=365).total_seconds():
        return f"{int(seconds/timedelta(days=30).total_seconds())}mo ago"
    else:
        return f"{int(seconds/timedelta(days=365).total_seconds())}y ago"

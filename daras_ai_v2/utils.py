from datetime import datetime


def get_relative_time(timestamp):
    now = datetime.now(timestamp.tzinfo)
    diff = now - timestamp

    seconds = diff.total_seconds()
    if seconds < 2:
        return "just now"
    if seconds < 60:
        return f"{int(seconds)}s ago"
    elif seconds < 3600:
        return f"{int(seconds/60)}m ago"
    elif seconds < 86400:
        return f"{int(seconds/3600)}h ago"
    elif seconds < 2592000:
        return f"{int(seconds/86400)}d ago"
    elif seconds < 31536000:
        return f"{int(seconds/2592000)}mo ago"
    else:
        return f"{int(seconds/31536000)}y ago"

from furl import furl

import gooey_gui as gui

YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com"}


def youtube_embed_url(url: str) -> str | None:
    """The iframe url for a YouTube link, or None if it isn't one. A `<video>` cannot
    play a YouTube page. Playlist and start-time params are dropped."""
    f = furl(url)
    if f.host == "youtu.be":
        video_id = f.path.segments[0] if f.path.segments else None
    elif f.host in YOUTUBE_HOSTS:
        segments = f.path.segments
        if segments[:1] == ["watch"]:
            video_id = f.args.get("v")
        elif len(segments) >= 2 and segments[0] in ("embed", "shorts", "live"):
            video_id = segments[1]
        else:
            video_id = None
    else:
        return None
    if not video_id:
        return None
    return f"https://www.youtube.com/embed/{video_id}"


def youtube_video(video_id: str):
    gui.markdown(
        f"""
        <div style="position: relative; padding-bottom: 56.25%; height: 0;">
        <iframe src="https://www.youtube.com/embed/{video_id}" title="YouTube video player" frameborder="0" webkitallowfullscreen mozallowfullscreen allowfullscreen allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%;">
        </iframe></div>
        """,
        unsafe_allow_html=True,
    )


def loom_video(video_id: str):
    gui.markdown(
        f"""
        <div style="position: relative; padding-bottom: 56.25%; height: 0;"><iframe src="https://www.loom.com/embed/{video_id}" frameborder="0" webkitallowfullscreen mozallowfullscreen allowfullscreen style="position: absolute; top: 0; left: 0; width: 100%; height: 100%;"></iframe></div>
        """,
        unsafe_allow_html=True,
    )

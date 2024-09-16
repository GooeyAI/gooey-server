import os
import traceback

from furl import furl

from daras_ai_v2 import settings

GITHUB_REPO = "https://github.com/GooeyAI/gooey-server/"
_base_dir = str(settings.BASE_DIR)


def github_url_for_exc(exc: Exception) -> str | None:
    for frame in reversed(traceback.extract_tb(exc.__traceback__)):
        if not frame.filename.startswith(_base_dir):
            continue
        return github_url_for_file(frame.filename, frame.lineno)
    return GITHUB_REPO


def github_url_for_file(filename: str, lineno: str | None = None) -> str:
    ref = (os.environ.get("CAPROVER_GIT_COMMIT_SHA") or "master").strip()
    path = os.path.relpath(filename, _base_dir)
    return str(
        furl(GITHUB_REPO, fragment_path=lineno and f"L{lineno}") / "blob" / ref / path
    )

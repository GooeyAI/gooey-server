import google.auth
from google.auth.transport.requests import AuthorizedSession

_session = None


def get_google_auth_session() -> tuple[AuthorizedSession, str]:
    global _session

    if _session is None:
        creds, project = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        # takes care of refreshing the token and adding it to request headers
        _session = AuthorizedSession(credentials=creds), project

    return _session

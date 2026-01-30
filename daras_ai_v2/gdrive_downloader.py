import typing
from functools import wraps
import requests
from furl import furl

from daras_ai_v2 import settings
from daras_ai_v2.exceptions import UserError, raise_for_status
from daras_ai_v2.functional import flatmap_parallel
from functions.composio_tools import (
    get_composio_connected_accounts,
    get_or_create_composio_auth_config,
)

if typing.TYPE_CHECKING:
    pass

DOCS_EXPORT_MIMETYPES = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.google-apps.drawing": "application/pdf",
}


def is_gdrive_url(f: furl) -> bool:
    return f.host in ["drive.google.com", "docs.google.com"]


def is_gdrive_presentation_url(f: furl) -> bool:
    return f.host == "docs.google.com" and "presentation" in f.path.segments


def url_to_gdrive_file_id(f: furl) -> str:
    # extract google drive file ID
    try:
        # https://drive.google.com/u/0/uc?id=FILE_ID&...
        file_id = f.query.params["id"]
    except KeyError:
        # https://drive.google.com/file/d/FILE_ID/...
        # https://docs.google.com/document/d/FILE_ID/...
        try:
            file_id = f.path.segments[f.path.segments.index("d") + 1]
        except (IndexError, ValueError):
            raise UserError(f"Bad google drive link: {str(f)!r}")
    return file_id


def gdrive_list_urls_of_files_in_folder(f: furl, max_depth: int = 4) -> list[str]:
    from googleapiclient import discovery

    if max_depth <= 0:
        return []
    assert f.host == "drive.google.com", f"Bad google drive folder url: {f}"
    # get drive folder id from url (e.g. https://drive.google.com/drive/folders/1Xijcsj7oBvDn1OWx4UmNAT8POVKG4W73?usp=drive_link)
    folder_id = f.path.segments[-1]
    service = discovery.build("drive", "v3")
    request = service.files().list(
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
        q=f"'{folder_id}' in parents",
        fields="files(mimeType,webViewLink)",
    )
    response = request.execute()
    files = response.get("files", [])
    urls = flatmap_parallel(
        lambda file: (
            gdrive_list_urls_of_files_in_folder(furl(url), max_depth=max_depth - 1)
            if (
                (url := file.get("webViewLink"))
                and file.get("mimeType") == "application/vnd.google-apps.folder"
            )
            else [url]
        ),
        files,
    )
    return filter(None, urls)


AUTH_STATUS_CODES = {401, 403, 404}


def _gdrive_api_wrapper(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except requests.HTTPError as err:
            if (
                err.response is None
                or err.response.status_code not in AUTH_STATUS_CODES
            ):
                raise
            if not settings.COMPOSIO_API_KEY:
                raise
            from composio import Composio
            from celeryapp.tasks import get_running_saved_run

            sr = get_running_saved_run()
            if not sr or not sr.workspace_id:
                raise

            composio = Composio()
            tokens, user_id, auth_config, redirect_url = composio_gdrive_tokens(
                composio, sr
            )

            for token in tokens:
                try:
                    return fn(*args, session=composio_gdrive_session(token), **kwargs)
                except requests.HTTPError as e:
                    if (
                        e.response is None
                        or e.response.status_code not in AUTH_STATUS_CODES
                    ):
                        raise

            connection_request = composio.connected_accounts.initiate(
                user_id=user_id,
                auth_config_id=auth_config.id,
                callback_url=redirect_url,
                allow_multiple=True,
            )
            raise UserError(
                f"This file is not accessible by your account or it was deleted. Please re-authenticate {connection_request.redirect_url}"
            ) from err

    return wrapper


@_gdrive_api_wrapper
def gdrive_download(
    f: furl,
    mime_type: str,
    export_links: typing.Optional[dict] = None,
    *,
    session: requests.Session | None = None,
) -> tuple[bytes, str]:
    if session is None:
        session = default_gdrive_session()
    file_id = url_to_gdrive_file_id(f)
    export_mime_type = DOCS_EXPORT_MIMETYPES.get(mime_type, mime_type)
    if f.host != "drive.google.com":
        f_url_export = export_links and export_links.get(export_mime_type, None)
        if f_url_export:
            r = session.get(f_url_export)
            raise_for_status(r)
            return r.content, export_mime_type
        else:
            r = gdrive_file_api_get(
                session,
                path=[file_id, "export"],
                params=dict(mimeType=export_mime_type),
            )
            return r.content, export_mime_type
    else:
        r = gdrive_file_api_get(
            session,
            path=[file_id],
            params=dict(alt="media", supportsAllDrives="true"),
        )
        return r.content, mime_type


@_gdrive_api_wrapper
def gdrive_metadata(
    file_id: str,
    *,
    fields: str = "name,md5Checksum,modifiedTime,mimeType,size,exportLinks",
    session: requests.Session | None = None,
) -> dict:
    if session is None:
        session = default_gdrive_session()
    return gdrive_file_api_get(
        session, path=[file_id], params=dict(supportsAllDrives="true", fields=fields)
    ).json()


def gdrive_file_api_get(
    session: requests.Session,
    path: list[str],
    params: dict[str, str] | None = None,
) -> requests.Response:
    f = furl("https://www.googleapis.com/drive/v3/files")
    f.path.segments.extend(path)
    r = session.get(str(f), params=params)
    raise_for_status(r)
    return r


def default_gdrive_session() -> requests.Session:
    from daras_ai_v2.asr import get_google_auth_session

    return get_google_auth_session("https://www.googleapis.com/auth/drive.readonly")[0]


def composio_gdrive_session(token: str) -> requests.Session:
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {token}"
    return session


def composio_gdrive_tokens(composio, sr):
    from functions.models import FunctionScopes
    from daras_ai_v2.base import SUBMIT_AFTER_LOGIN_Q

    user_id = FunctionScopes.get_user_id_for_scope(
        FunctionScopes.workspace, workspace=sr.workspace
    )
    auth_config = get_or_create_composio_auth_config(composio, "GOOGLEDRIVE")
    redirect_url = sr.get_app_url({SUBMIT_AFTER_LOGIN_Q: "1"})
    connected_accounts = get_composio_connected_accounts(
        composio,
        auth_config=auth_config,
        redirect_url=redirect_url,
        user_id=user_id,
    )
    tokens = [
        token
        for item in connected_accounts
        if (token := getattr(getattr(item.state, "val", None), "access_token", None))
    ]
    return tokens, user_id, auth_config, redirect_url

import base64

import requests
from furl import furl

from bots.models import SavedRun
from daras_ai_v2.exceptions import UserError
from daras_ai_v2.exceptions import raise_for_status, OneDriveAuth
from routers.onedrive_api import (
    generate_onedrive_auth_url,
    get_access_token_from_refresh_token,
)


def is_onedrive_url(f: furl) -> bool:
    if f.host == "1drv.ms":
        return True
    elif f.host.endswith(".sharepoint.com"):
        return True
    elif f.host == "onedrive.live.com":
        raise UserError(
            "Direct onedrive.live.com links are not supported. Please provide a shareable OneDrive link (from Share > Copy Link) E.g. https://1drv.ms/xxx"
        )


_url_encode_translation = str.maketrans({"/": "_", "+": "-", "=": ""})


def encode_onedrive_url(sharing_url: str) -> str:
    # https://learn.microsoft.com/en-us/onedrive/developer/rest-api/api/shares_get
    base64_value = base64.b64encode(sharing_url.encode()).decode()
    encoded_url = base64_value.translate(_url_encode_translation)
    return f"u!{encoded_url}"


def onedrive_download(mime_type: str, export_links: dict):
    download_url = export_links.get(mime_type)
    if not download_url:
        raise ValueError(
            "Download URL not found in export_links. Cannot download file."
        )
    r = requests.get(download_url)
    raise_for_status(r)
    file_content = r.content
    return file_content, mime_type


def onedrive_meta(f_url: str, sr: SavedRun, *, try_refresh: bool = True):
    # check if saved run workspace has onedrive_access_token and onedrive_refresh_token
    if not (
        sr.workspace
        and sr.workspace.onedrive_access_token
        and sr.workspace.onedrive_refresh_token
    ):
        raise OneDriveAuth(generate_onedrive_auth_url(sr.id))
    try:
        encoded_url = encode_onedrive_url(f_url)
        headers = {"Authorization": f"Bearer {sr.workspace.onedrive_access_token}"}
        r = requests.get(
            f"https://graph.microsoft.com/v1.0/shares/{encoded_url}/driveItem",
            headers=headers,
        )
        raise_for_status(r)
        metadata = r.json()

        if "folder" in metadata:
            raise UserError(
                "Folders & OneNote files are not supported yet. Please remove them from your Knowledge base."
            )

        return metadata

    except requests.HTTPError as e:
        if e.response.status_code == 401 and try_refresh:
            try:
                (
                    sr.workspace.onedrive_access_token,
                    sr.workspace.onedrive_refresh_token,
                ) = get_access_token_from_refresh_token(
                    sr.workspace.onedrive_refresh_token
                )
                sr.workspace.save(update_fields=["onedrive_access_token"])
                return onedrive_meta(f_url, sr, try_refresh=False)
            except requests.HTTPError:
                raise OneDriveAuth(generate_onedrive_auth_url(sr.id))

        # https://learn.microsoft.com/en-us/graph/errors
        elif e.response.status_code in [403, 400, 405, 410, 422]:
            raise UserError(
                message=f"""
<p>
<a href="{f_url}" target="_blank">This document </a> is not accessible by "{sr.workspace.onedrive_user_name}".
Please share the document with this account (Share > Manage Access).
</p>
<p>
Alternatively, <a href="{generate_onedrive_auth_url(sr.id)}" target="_blank">Login</a> with a OneDrive account that can access this file.
Note that you can only be logged in to one OneDrive account at a time.
</p>
"""
            ) from e

        else:
            raise

from furl import furl
import requests
import base64
from workspaces.models import Workspace
from daras_ai_v2.exceptions import UserError
from daras_ai_v2.exceptions import raise_for_status, OneDriveAuth
from routers.onedrive_api import (
    generate_onedrive_auth_url,
    get_access_token_from_refresh_token,
)
from loguru import logger


def is_onedrive_url(f: furl) -> bool:
    if f.host == "1drv.ms":
        return True
    elif f.host == "onedrive.live.com":
        raise UserError(
            "Please provide a shareable OneDrive link (1drv.ms). Direct onedrive.live.com links are not supported."
        )


def encode_onedrive_url(sharing_url: str) -> str:
    # https://learn.microsoft.com/en-us/onedrive/developer/rest-api/api/shares_get

    base64_value = base64.b64encode(sharing_url.encode("utf-8")).decode("utf-8")
    encoded_url = base64_value.rstrip("=").replace("/", "_").replace("+", "-")
    return f"u!{encoded_url}"


def onedrive_download(f: furl, mime_type: str, export_links: dict):
    if export_links is None or "downloadUrl" not in export_links:
        raise ValueError(
            "Download URL not found in export_links. Cannot download file."
        )
    download_url = export_links["downloadUrl"]
    r = requests.get(download_url, stream=True)
    raise_for_status(r)
    file_content = r.content
    return file_content, mime_type


def onedrive_meta(
    f_url: str, current_workspace: Workspace, current_app_url: str, retries: int = 1
):
    # check if current_workspace have the field current_workspace.onedrive_access_token or onedrive_access_token.refresh_token
    if not (
        current_workspace.onedrive_access_token
        and current_workspace.onedrive_refresh_token
    ):
        raise OneDriveAuth(generate_onedrive_auth_url(current_app_url))
    try:
        encoded_url = encode_onedrive_url(f_url)
        headers = {"Authorization": f"Bearer {current_workspace.onedrive_access_token}"}
        r = requests.get(
            f"https://graph.microsoft.com/v1.0/shares/{encoded_url}/driveItem",
            headers=headers,
        )
        raise_for_status(r)
        metadata = r.json()

        if "folder" in metadata:
            raise UserError("Folders are not supported .")

        return metadata
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401 and retries > 0:
            try:
                current_workspace.onedrive_access_token = (
                    get_access_token_from_refresh_token(
                        current_workspace.onedrive_refresh_token,
                        current_app_url,
                    )
                )
                current_workspace.save(update_fields=["onedrive_access_token"])
                return onedrive_meta(
                    f_url, current_workspace, current_app_url, retries - 1
                )
            except Exception:
                raise OneDriveAuth(generate_onedrive_auth_url(current_app_url))

        elif e.response.status_code == 403:
            raise UserError(
                "make sure the document is accessible from logged in microsoft account"
            )
        else:
            raise e

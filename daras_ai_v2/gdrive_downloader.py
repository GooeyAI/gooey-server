import io
import mimetypes
from furl import furl
import requests

from daras_ai_v2.exceptions import UserError
from daras_ai_v2.functional import flatmap_parallel
from daras_ai_v2.exceptions import raise_for_status


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


def gdrive_download(f: furl, mime_type: str, export_links: dict) -> tuple[bytes, str]:
    from googleapiclient import discovery
    from googleapiclient.http import MediaIoBaseDownload

    # get drive file id
    file_id = url_to_gdrive_file_id(f)
    # get metadata
    service = discovery.build("drive", "v3")

    if f.host != "drive.google.com":
        # export google docs to appropriate type
        export_mime_type, _, is_google_workspace_doc = docs_export_mimetype(
            f, mime_type
        )

        if is_google_workspace_doc and (
            f_url_export := export_links.get(export_mime_type, None)
        ):
            r = requests.get(f_url_export)
            file_bytes = r.content
            raise_for_status(r, is_user_url=True)
            return file_bytes, export_mime_type

    request = service.files().get_media(
        fileId=file_id,
        supportsAllDrives=True,
    )
    # download
    file = io.BytesIO()
    downloader = MediaIoBaseDownload(file, request)
    done = False
    while done is False:
        _, done = downloader.next_chunk()
        # print(f"Download {int(status.progress() * 100)}%")
    file_bytes = file.getvalue()

    return file_bytes, mime_type


def docs_export_mimetype(f: furl, mime_type) -> tuple[str, str, bool]:
    """
    return the mimetype to export google docs - https://developers.google.com/drive/api/guides/ref-export-formats

    Args:
        f (furl): google docs link

    Returns:
        tuple[str, str]: (mime_type, extension, is_google_workspace_supported)
    """

    supported_mimetypes = {
        "application/vnd.google-apps.spreadsheet",
        "application/vnd.google-apps.presentation",
        "application/vnd.google-apps.drawing",
        "application/vnd.google-apps.document",
    }

    is_google_workspace_supported = mime_type in supported_mimetypes

    if is_google_workspace_supported:
        if "document" in f.path.segments:
            mime_type = "text/plain"
            ext = ".txt"
        elif "spreadsheets" in f.path.segments:
            mime_type = "text/csv"
            ext = ".csv"
        elif "presentation" in f.path.segments:
            mime_type = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            ext = ".pptx"
        elif "drawings" in f.path.segments:
            mime_type = "application/pdf"
            ext = ".pdf"
        else:
            raise ValueError(f"Not sure how to export google docs url: {str(f)!r}")
    else:
        ext = f".{mimetypes.guess_extension(mime_type)}" or ""
    return mime_type, ext, is_google_workspace_supported


def gdrive_metadata(file_id: str) -> dict:
    from googleapiclient import discovery

    service = discovery.build("drive", "v3")
    metadata = (
        service.files()
        .get(
            supportsAllDrives=True,
            fileId=file_id,
            fields="name,md5Checksum,modifiedTime,mimeType,size,exportLinks",
        )
        .execute()
    )
    return metadata

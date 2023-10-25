import io
import mimetypes

from furl import furl
from googleapiclient import discovery
from googleapiclient.http import MediaIoBaseDownload


def is_gdrive_url(f: furl) -> bool:
    return f.host in ["drive.google.com", "docs.google.com"]


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
            raise ValueError(f"Bad google drive link: {str(f)!r}")
    return file_id


def gdrive_download(f: furl, mime_type: str) -> tuple[bytes, str]:
    # get drive file id
    file_id = url_to_gdrive_file_id(f)
    # get metadata
    service = discovery.build("drive", "v3")
    # get files in drive directly
    if f.host == "drive.google.com":
        request = service.files().get_media(
            fileId=file_id,
            supportsAllDrives=True,
        )
        ext = mimetypes.guess_extension(mime_type)
    # export google docs to appropriate type
    else:
        mime_type, ext = docs_export_mimetype(f)
        request = service.files().export_media(
            fileId=file_id,
            mimeType=mime_type,
        )
    # download
    file = io.BytesIO()
    downloader = MediaIoBaseDownload(file, request)
    done = False
    while done is False:
        _, done = downloader.next_chunk()
        # print(f"Download {int(status.progress() * 100)}%")
    f_bytes = file.getvalue()
    return f_bytes, ext


def docs_export_mimetype(f: furl) -> tuple[str, str]:
    """
    return the mimetype to export google docs - https://developers.google.com/drive/api/guides/ref-export-formats

    Args:
        f (furl): google docs link

    Returns:
        tuple[str, str]: (mime_type, extension)
    """
    if "document" in f.path.segments:
        mime_type = "text/plain"
        ext = ".txt"
    elif "spreadsheets" in f.path.segments:
        mime_type = "text/csv"
        ext = ".csv"
    elif "presentation" in f.path.segments:
        mime_type = "application/pdf"
        ext = ".pdf"
    elif "drawings" in f.path.segments:
        mime_type = "application/pdf"
        ext = ".pdf"
    else:
        raise ValueError(f"Not sure how to export google docs url: {str(f)!r}")
    return mime_type, ext


def gdrive_metadata(file_id: str) -> dict:
    service = discovery.build("drive", "v3")
    metadata = (
        service.files()
        .get(
            supportsAllDrives=True,
            fileId=file_id,
            fields="name,md5Checksum,modifiedTime,mimeType",
        )
        .execute()
    )
    return metadata

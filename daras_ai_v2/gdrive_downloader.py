import io

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


def gdrive_download(f: furl) -> bytes:
    # get drive file id
    file_id = url_to_gdrive_file_id(f)
    # get metadata
    service = discovery.build("drive", "v3")
    # get files in drive directly
    if f.host == "drive.google.com":
        request = service.files().get_media(fileId=file_id)
    # export google docs to text
    else:
        request = service.files().export_media(fileId=file_id, mimeType="text/plain")
    # download
    file = io.BytesIO()
    downloader = MediaIoBaseDownload(file, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
        # print(f"Download {int(status.progress() * 100)}%")
    f_bytes = file.getvalue()
    return f_bytes


def gdrive_metadata(file_id: str) -> dict:
    service = discovery.build("drive", "v3")
    return (
        service.files()
        .get(
            fileId=file_id,
            fields="name,md5Checksum,modifiedTime",
        )
        .execute()
    )

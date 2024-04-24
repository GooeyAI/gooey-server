import random
import threading
import typing

import requests
from aifail import retry_if
from django.db.models import IntegerChoices
from furl import furl
from pydantic import BaseModel

import gooey_ui as st
from bots.models import Workflow
from daras_ai.image_input import upload_file_from_bytes
from daras_ai_v2 import settings
from daras_ai_v2.asr import (
    google_translate_language_selector,
    AsrModels,
    run_asr,
    download_youtube_to_wav_url,
    run_google_translate,
    audio_url_to_wav,
)
from daras_ai_v2.azure_doc_extract import (
    azure_doc_extract_page_num,
)
from daras_ai_v2.base import BasePage
from daras_ai_v2.doc_search_settings_widgets import document_uploader
from daras_ai_v2.enum_selector_widget import enum_selector
from daras_ai_v2.exceptions import raise_for_status
from daras_ai_v2.fake_user_agents import FAKE_USER_AGENTS
from daras_ai_v2.functional import (
    apply_parallel,
    flatapply_parallel,
)
from daras_ai_v2.gdrive_downloader import is_gdrive_url, gdrive_download
from daras_ai_v2.glossary import glossary_input
from daras_ai_v2.language_model import run_language_model, LargeLanguageModels
from daras_ai_v2.language_model_settings_widgets import language_model_settings
from daras_ai_v2.loom_video_widget import youtube_video
from daras_ai_v2.settings import service_account_key_path
from daras_ai_v2.vector_search import (
    add_page_number_to_pdf,
    yt_dlp_get_video_entries,
    doc_url_to_file_metadata,
    get_pdf_num_pages,
)
from recipes.DocSearch import render_documents

DEFAULT_YOUTUBE_BOT_META_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/ddc8ffac-93fb-11ee-89fb-02420a0001cb/Youtube%20transcripts.jpg.png"


class Columns(IntegerChoices):
    webpage_url = 1, "url"
    title = 2, "title"
    final_output = 3, "snippet/sections"
    description = 4, "Description"
    content_url = 5, "Content URL"
    transcript = 6, "Transcript"
    translation = 7, "Translation"
    summary = 8, "Summarized"
    status = 9, "Status"


class DocExtractPage(BasePage):
    title = "Synthetic Data Maker for Videos & PDFs"
    explore_image = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/aeb83ee8-889e-11ee-93dc-02420a000143/Youtube%20transcripts%20GPT%20extractions.png.png"
    workflow = Workflow.DOC_EXTRACT
    slug_versions = [
        "doc-extract",
        "youtube-bot",
        "doc-extract",
    ]
    price = 500

    class RequestModel(BaseModel):
        documents: list[str]

        sheet_url: str | None

        selected_asr_model: typing.Literal[tuple(e.name for e in AsrModels)] | None
        # language: str | None
        google_translate_target: str | None
        glossary_document: str | None

        task_instructions: str | None

        selected_model: (
            typing.Literal[tuple(e.name for e in LargeLanguageModels)] | None
        )
        avoid_repetition: bool | None
        num_outputs: int | None
        quality: float | None
        max_tokens: int | None
        sampling_temperature: float | None

    class ResponseModel(BaseModel):
        pass

    def preview_image(self, state: dict) -> str | None:
        return DEFAULT_YOUTUBE_BOT_META_IMG

    def render_form_v2(self):
        document_uploader(
            "#### 🤖 Youtube/PDF/Drive URLs",
            accept=("audio/*", "application/pdf", "video/*"),
        )
        st.text_input(
            "#### 📊 Google Sheets URL",
            key="sheet_url",
        )

    def validate_form_v2(self):
        assert st.session_state.get("documents"), "Please enter Youtube/PDF/Drive URLs"
        assert st.session_state.get("sheet_url"), "Please enter a Google Sheet URL"

    def preview_description(self, state: dict) -> str:
        return "Transcribe YouTube videos in any language with Whisper, Google Chirp & more, run your own GPT4 prompt on each transcript and save it all to a Google Sheet. Perfect for making a YouTube-based dataset to create your own chatbot or enterprise copilot (ie. just add the finished Google sheet url to the doc section in https://gooey.ai/copilot)."

    def render_example(self, state: dict):
        render_documents(state)
        st.write("**Google Sheets URL**")
        st.write(state.get("sheet_url"))

    def render_usage_guide(self):
        youtube_video("p7ZLb-loR_4")

    def render_settings(self):
        st.text_area(
            "### 👩‍🏫 Task Instructions",
            key="task_instructions",
            height=300,
        )
        language_model_settings()
        "##### Document AI Model"
        enum_selector(AsrModels, label="##### ASR Model", key="selected_asr_model")
        st.write("---")
        google_translate_language_selector()
        glossary_input()
        st.write("---")
        # enum_selector(
        #     AsrOutputFormat, label="###### Output Format", key="output_format"
        # )

    def related_workflows(self) -> list:
        from recipes.asr_page import AsrPage
        from recipes.CompareLLM import CompareLLMPage
        from recipes.DocSearch import DocSearchPage
        from recipes.VideoBots import VideoBotsPage

        return [VideoBotsPage, AsrPage, CompareLLMPage, DocSearchPage]

    def run(self, state: dict) -> typing.Iterator[str | None]:
        import gspread.utils

        request: DocExtractPage.RequestModel = self.RequestModel.parse_obj(state)

        entries = yield from flatapply_parallel(
            extract_info,
            request.documents,
            message="Extracting metadata...",
            max_workers=50,
        )

        yield "Preparing sheet..."
        spreadsheet_id = gspread.utils.extract_id_from_url(request.sheet_url)
        ensure_header(spreadsheet_id)
        row_numbers = init_sheet(spreadsheet_id, entries)

        yield from apply_parallel(
            lambda entry, row: process_entry(
                spreadsheet_id=spreadsheet_id,
                entry=entry,
                row=row,
                request=request,
            ),
            entries,
            row_numbers,
            max_workers=4,
            message="Updating sheet...",
        )


def ensure_header(spreadsheet_id):
    get_spreadsheet_service().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"A1:{col_i2a(len(Columns))}1",
        body={"values": [Columns.labels]},
        valueInputOption="RAW",
    ).execute()


def init_sheet(spreadsheet_id: str, entries: list[dict | None]) -> list[int | None]:
    import gspread.utils

    start_row = 2
    spreadsheets = get_spreadsheet_service()

    # find existing rows
    values = [
        row[0].strip() if row else ""
        for row in spreadsheets.values()
        .get(
            spreadsheetId=spreadsheet_id,
            range=f"{col_i2a(Columns.webpage_url.value)}{start_row}:{col_i2a(Columns.webpage_url.value)}",
        )
        .execute()
        .get("values", [[]])
    ]

    row_numbers = [None] * len(entries)
    to_append = []
    for i, entry in enumerate(entries):
        try:
            idx = values.index(entry["webpage_url"])
        except ValueError:
            row = [""] * len(Columns)
            row[Columns.webpage_url.value - 1] = entry["webpage_url"]
            to_append.append(row)
        else:
            row_numbers[i] = idx + start_row

    # append all missing rows
    response = (
        spreadsheets.values()
        .append(
            spreadsheetId=spreadsheet_id,
            range=f"A{start_row}:A",
            body={"values": to_append},
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
        )
        .execute()
    )
    updated_range = response["updates"]["updatedRange"].split("!")[1]
    start_idx = gspread.utils.a1_range_to_grid_range(updated_range)["startRowIndex"]
    for i, row in enumerate(row_numbers):
        if row is None:
            start_idx += 1
            row_numbers[i] = start_idx

    # update all rows with metadata
    spreadsheets.values().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={
            "valueInputOption": "RAW",
            "data": [
                {
                    "range": f"{col_i2a(col)}{row}:{col_i2a(col)}{row}",
                    "values": [[value]],
                }
                for row, entry in zip(row_numbers, entries)
                for col, value in [
                    (Columns.webpage_url.value, entry["webpage_url"]),
                    (Columns.title.value, entry.get("title", "")),
                    (Columns.description.value, entry.get("description", "")),
                    (Columns.status.value, "Pending"),
                ]
            ],
        },
    ).execute()

    return row_numbers


def col_i2a(col: int) -> str:
    div = col
    label = ""
    while div:
        (div, mod) = divmod(div, 26)
        if mod == 0:
            mod = 26
            div -= 1
        label = chr(mod + 64) + label
    return label


def extract_info(url: str) -> list[dict | None]:
    if is_yt_url(url):
        return yt_dlp_get_video_entries(url)

        # https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/options.py
        params = dict(ignoreerrors=True, check_formats=False)
        with yt_dlp.YoutubeDL(params) as ydl:
            data = ydl.extract_info(url, download=False)
        if data:
            entries = data.get("entries", [data])
            return [e for e in entries if e]
        else:
            return [{"webpage_url": url, "title": "Youtube Video"}]

    # assume it's a direct link
    file_meta = doc_url_to_file_metadata(url)
    assert file_meta.mime_type, f"Could not determine mime type for {url}"

    if "application/pdf" in file_meta.mime_type:
        f = furl(url)
        if is_gdrive_url(f):
            f_bytes, _ = gdrive_download(f, file_meta.mime_type)
            content_url = upload_file_from_bytes(
                file_meta.name, f_bytes, content_type=file_meta.mime_type
            )
        else:
            r = requests.get(
                url,
                headers={"User-Agent": random.choice(FAKE_USER_AGENTS)},
                timeout=settings.EXTERNAL_REQUEST_TIMEOUT_SEC,
            )
            raise_for_status(r)
            f_bytes = r.content
            content_url = url
        num_pages = get_pdf_num_pages(f_bytes)
        return [
            {
                "webpage_url": add_page_number_to_pdf(f, page_num).url,
                "title": f"{file_meta.name}, page {page_num}",
                "doc_meta": file_meta,
                # "pdf_page": page,
                "content_url": add_page_number_to_pdf(content_url, page_num).url,
                "page_num": page_num,
            }
            for i in range(num_pages)
            if (page_num := i + 1)
        ]
    else:
        return [
            {
                "webpage_url": url,
                "title": file_meta.name,
                "doc_meta": file_meta,
            },
        ]


def process_entry(
    spreadsheet_id: str,
    row: int,
    entry: dict | None,
    request: DocExtractPage.RequestModel,
):
    if not (entry and entry.get("webpage_url")):
        return

    try:
        for status in process_source(
            request=request,
            spreadsheet_id=spreadsheet_id,
            row=row,
            entry=entry,
        ):
            update_cell(spreadsheet_id, row, Columns.status.value, status)
    except:
        update_cell(spreadsheet_id, row, Columns.status.value, "Error")
        raise
    else:
        update_cell(spreadsheet_id, row, Columns.status.value, "Done")


def process_source(
    *,
    request: DocExtractPage.RequestModel,
    spreadsheet_id: str,
    row: int,
    entry: dict,
) -> typing.Iterator[str | None]:
    webpage_url = entry["webpage_url"]
    doc_meta = entry.get("doc_meta")

    # get the values in existing row
    existing_values = (
        get_spreadsheet_service()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=f"{row}:{row}")
        .execute()
        .get("values", [[]])[0]
    )
    # pad with None to avoid index errors
    existing_values = (
        [None] + existing_values + [None] * max(len(Columns) - len(existing_values), 0)
    )

    content_url = existing_values[Columns.content_url.value]
    is_yt = is_yt_url(webpage_url)
    is_pdf = doc_meta and "application/pdf" in doc_meta.mime_type
    is_video = doc_meta and (
        "video/" in doc_meta.mime_type or "audio/" in doc_meta.mime_type
    )
    if not content_url:
        yield "Downloading"
        if is_yt:
            content_url, _ = download_youtube_to_wav_url(webpage_url)
        elif is_video:
            f = furl(webpage_url)
            if is_gdrive_url(f):
                f_bytes, _ = gdrive_download(f, doc_meta.mime_type)
                webpage_url = upload_file_from_bytes(
                    doc_meta.name, f_bytes, content_type=doc_meta.mime_type
                )
            content_url, _ = audio_url_to_wav(webpage_url)
        elif is_pdf:
            content_url = entry.get("content_url") or webpage_url
        else:
            raise NotImplementedError(
                f"Unsupported type {doc_meta and doc_meta.mime_type} for {webpage_url}"
            )
        update_cell(spreadsheet_id, row, Columns.content_url.value, content_url)

    transcript = existing_values[Columns.transcript.value]
    if not transcript:
        if is_yt or is_video:
            yield "Transcribing"
            transcript = run_asr(content_url, request.selected_asr_model)
        elif is_pdf:
            yield "Extracting PDF"
            transcript = azure_doc_extract_page_num(content_url, entry.get("page_num"))
        else:
            raise NotImplementedError(
                f"Unsupported type {doc_meta and doc_meta.mime_type} for {webpage_url}"
            )
        update_cell(spreadsheet_id, row, Columns.transcript.value, transcript)

    if is_pdf:
        final_col_name = "sections"
    else:
        final_col_name = "snippet"
    final_value = transcript

    if request.google_translate_target:
        translation = existing_values[Columns.translation.value]
        if not translation:
            yield "Translating"
            translation = run_google_translate(
                texts=[transcript],
                target_language=request.google_translate_target,
                # source_language=request.language,
                glossary_url=request.glossary_document,
            )[0]
            update_cell(spreadsheet_id, row, Columns.translation.value, translation)
        final_value = translation
    else:
        translation = transcript
        update_cell(spreadsheet_id, row, Columns.translation.value, "")

    summary = existing_values[Columns.summary.value]
    if request.task_instructions:
        if not summary:
            yield "Summarizing"
            prompt = request.task_instructions.strip() + "\n\n" + translation
            summary = "\n---\n".join(
                run_language_model(
                    model=request.selected_model,
                    quality=request.quality,
                    num_outputs=request.num_outputs,
                    temperature=request.sampling_temperature,
                    prompt=prompt,
                    max_tokens=request.max_tokens,
                    avoid_repetition=request.avoid_repetition,
                )
            )
            update_cell(spreadsheet_id, row, Columns.summary.value, summary)
        if final_col_name != "sections":
            final_value = f"content={final_value}\ncontent={summary}"
            final_col_name = "sections"
        else:
            final_value = f"{final_value}\ncontent={summary}"
    else:
        update_cell(spreadsheet_id, row, Columns.summary.value, "")

    update_cell(spreadsheet_id, 1, Columns.final_output.value, final_col_name)
    update_cell(spreadsheet_id, row, Columns.final_output.value, final_value)


def google_api_should_retry(e: Exception) -> bool:
    from googleapiclient.errors import HttpError

    return (
        isinstance(e, HttpError)
        and (e.resp.status in (408, 429) or e.resp.status > 500)
    ) or isinstance(e, TimeoutError)


@retry_if(google_api_should_retry)
def update_cell(spreadsheet_id: str, row: int, col: int, value: str):
    get_spreadsheet_service().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{col_i2a(col)}{row}:{col_i2a(col)}{row}",
        body={"values": [[value]]},
        valueInputOption="RAW",
    ).execute()


def is_yt_url(url: str) -> bool:
    return "youtube.com" in url or "youtu.be" in url


threadlocal = threading.local()


def get_spreadsheet_service():
    from oauth2client.service_account import ServiceAccountCredentials
    from googleapiclient.discovery import build

    try:
        return threadlocal.spreadsheets
    except AttributeError:
        # Authenticate with the Google Sheets API using a service account
        scope = [
            "https://www.googleapis.com/auth/drive",
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_name(
            service_account_key_path, scope
        )
        service = build("sheets", "v4", credentials=creds)
        threadlocal.spreadsheets = service.spreadsheets()
        return threadlocal.spreadsheets

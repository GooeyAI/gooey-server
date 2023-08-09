import threading
import typing

from django.db.models import IntegerChoices
from furl import furl
from pydantic import BaseModel

import gooey_ui as st
from daras_ai.image_input import upload_file_from_bytes
from daras_ai_v2.asr import (
    google_translate_language_selector,
    AsrModels,
    run_asr,
    download_youtube_to_wav,
    run_google_translate,
    audio_to_wav,
)
from daras_ai_v2.base import BasePage
from daras_ai_v2.doc_search_settings_widgets import document_uploader
from daras_ai_v2.enum_selector_widget import enum_selector
from daras_ai_v2.functional import (
    apply_parallel,
    flatapply_parallel,
)
from daras_ai_v2.gdrive_downloader import is_gdrive_url, gdrive_download
from daras_ai_v2.language_model import run_language_model, LargeLanguageModels
from daras_ai_v2.language_model_settings_widgets import language_model_settings
from daras_ai_v2.settings import service_account_key_path
from daras_ai_v2.vector_search import doc_url_to_metadata
from recipes.DocSearch import render_documents


class Columns(IntegerChoices):
    video_url = 1, "Source"
    title = 2, "Title"
    description = 3, "Description"
    audio_url = 4, "Audio"
    transcript = 5, "Transcript"
    translation = 6, "Translation"
    summary = 7, "Summarized"
    status = 8, "Status"


class DocExtractPage(BasePage):
    title = "Youtube Transcripts + GPT extraction to Google Sheets"
    slug_versions = [
        "doc-extract",
        "youtube-bot",
    ]
    price = 500

    class RequestModel(BaseModel):
        documents: list[str]

        sheet_url: str | None

        selected_asr_model: typing.Literal[tuple(e.name for e in AsrModels)] | None
        # language: str | None
        google_translate_target: str | None

        task_instructions: str | None

        selected_model: typing.Literal[
            tuple(e.name for e in LargeLanguageModels)
        ] | None
        avoid_repetition: bool | None
        num_outputs: int | None
        quality: float | None
        max_tokens: int | None
        sampling_temperature: float | None

    class ResponseModel(BaseModel):
        pass

    def render_form_v2(self):
        document_uploader(
            "##### 🤖 Youtube URLS",
            accept=(".wav", ".ogg", ".mp3", ".aac", ".opus", ".oga", ".mp4", ".webm"),
        )
        st.text_input(
            "##### 📊 Google Sheets URL",
            key="sheet_url",
        )

    def validate_form_v2(self):
        assert st.session_state.get("documents"), "Please enter Youtube video URL/URLs"
        assert st.session_state.get("sheet_url"), "Please enter a Google Sheet URL"

    def preview_description(self, state: dict) -> str:
        return "Transcribe YouTube videos in any language with Whisper, Google Chirp & more, run your own GPT4 prompt on each transcript and save it all to a Google Sheet. Perfect for making a YouTube-based dataset to create your own chatbot or enterprise copilot (ie. just add the finished Google sheet url to the doc section in https://gooey.ai/copilot)."

    def render_example(self, state: dict):
        render_documents(state)
        st.write("**Google Sheets URL**")
        st.write(state.get("sheet_url"))

    def render_settings(self):
        st.text_area(
            "### 👩‍🏫 Task Instructions",
            key="task_instructions",
            height=300,
        )
        language_model_settings()
        enum_selector(AsrModels, label="##### ASR Model", key="selected_asr_model")
        st.write("---")
        google_translate_language_selector()
        st.write("---")
        # enum_selector(
        #     AsrOutputFormat, label="###### Output Format", key="output_format"
        # )

    def related_workflows(self) -> list:
        from recipes.asr import AsrPage
        from recipes.CompareLLM import CompareLLMPage
        from recipes.DocSearch import DocSearchPage
        from recipes.VideoBots import VideoBotsPage

        return [VideoBotsPage, AsrPage, CompareLLMPage, DocSearchPage]

    def run(self, state: dict) -> typing.Iterator[str | None]:
        import gspread.utils

        request: DocExtractPage.RequestModel = self.RequestModel.parse_obj(state)

        entries = yield from flatapply_parallel(
            extract_info, request.documents, message="Extracting metadata..."
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
            range=f"{col_i2a(Columns.video_url.value)}{start_row}:{col_i2a(Columns.video_url.value)}",
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
            row[Columns.video_url.value - 1] = entry["webpage_url"]
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
                    (Columns.video_url.value, entry["webpage_url"]),
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
        import yt_dlp

        # https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/options.py
        params = dict(ignoreerrors=True, check_formats=False)
        with yt_dlp.YoutubeDL(params) as ydl:
            data = ydl.extract_info(url, download=False)
        entries = data.get("entries", [data])
        return entries
    else:
        return [{"webpage_url": url}]  # assume it's a direct link


def process_entry(
    spreadsheet_id: str,
    row: int,
    entry: dict | None,
    request: DocExtractPage.RequestModel,
):
    if not entry:
        return
    webpage_url = entry.get("webpage_url")
    if not webpage_url:
        return

    try:
        for status in process_source(
            request=request,
            spreadsheet_id=spreadsheet_id,
            row=row,
            webpage_url=webpage_url,
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
    webpage_url: str,
) -> typing.Iterator[str | None]:
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

    audio_url = existing_values[Columns.audio_url.value]
    if not audio_url:
        yield "Downloading"
        if is_yt_url(webpage_url):
            audio_url, _ = download_youtube_to_wav(webpage_url)
        else:
            f = furl(webpage_url)
            if is_gdrive_url(f):
                doc_meta = doc_url_to_metadata(webpage_url)
                f_name = doc_meta.name
                update_cell(spreadsheet_id, row, Columns.title.value, f_name)
                f_bytes, _ = gdrive_download(f, doc_meta.mime_type)
                webpage_url = upload_file_from_bytes(
                    f_name, f_bytes, content_type=doc_meta.mime_type
                )
            audio_url, _ = audio_to_wav(webpage_url)
        update_cell(spreadsheet_id, row, Columns.audio_url.value, audio_url)

    transcript = existing_values[Columns.transcript.value]
    if not transcript:
        yield "Transcribing"
        transcript = run_asr(audio_url, request.selected_asr_model)
        update_cell(spreadsheet_id, row, Columns.transcript.value, transcript)

    if request.google_translate_target:
        translation = existing_values[Columns.translation.value]
        if not translation:
            yield "Translating"
            translation = run_google_translate(
                texts=[transcript],
                target_language=request.google_translate_target,
                # source_language=request.language,
            )[0]
            update_cell(spreadsheet_id, row, Columns.translation.value, translation)
    else:
        translation = transcript
        update_cell(spreadsheet_id, row, Columns.translation.value, "")

    summary = existing_values[Columns.summary.value]
    if not summary and request.task_instructions:
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

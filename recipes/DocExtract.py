import typing

from django.db.models import IntegerChoices
from furl import furl
from pydantic import BaseModel

import gooey_ui as st
from daras_ai.image_input import upload_file_from_bytes
from daras_ai_v2.asr import (
    AsrModels,
    run_asr,
    download_youtube_to_wav,
    audio_to_wav,
)
from daras_ai_v2.translate import (
    Translate,
    TranslateUI,
)
from daras_ai_v2.base import BasePage
from daras_ai_v2.doc_search_settings_widgets import document_uploader
from daras_ai_v2.enum_selector_widget import enum_selector
from daras_ai_v2.functional import map_parallel, flatmap_parallel
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
        )
        language_model_settings()
        enum_selector(AsrModels, label="##### ASR Model", key="selected_asr_model")
        st.write("---")
        TranslateUI.translate_language_selector(key="google_translate_target")
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
        request: DocExtractPage.RequestModel = self.RequestModel.parse_obj(state)

        worksheet = get_worksheet(request.sheet_url)

        # ensure column names are correct
        if worksheet.row_values(1)[: len(Columns)] != Columns.labels:
            worksheet.update("A1", [Columns.labels])

        yield "Extracting metadata..."
        entries = flatmap_parallel(extract_info, request.documents)

        yield "Updating sheet..."
        map_parallel(
            lambda entry: process_entry(
                entry=entry, worksheet=worksheet, request=request
            ),
            entries,
            max_workers=4,
        )


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


def process_entry(worksheet, entry: dict | None, request: DocExtractPage.RequestModel):
    import gspread.utils

    if not entry:
        return
    webpage_url = entry.get("webpage_url")
    if not webpage_url:
        return

    cell = worksheet.find(webpage_url)
    if cell:
        row = cell.row
    else:
        table_range = worksheet.append_row([])["updates"]["updatedRange"]
        cell = table_range.split("!")[-1]
        row = gspread.utils.a1_to_rowcol(cell)[0]

    worksheet.update_cells(
        [
            gspread.Cell(row, Columns.video_url.value, webpage_url),
            gspread.Cell(row, Columns.title.value, entry.get("title", "")),
            gspread.Cell(row, Columns.description.value, entry.get("description", "")),
        ],
    )

    try:
        for status in process_source(
            request=request,
            worksheet=worksheet,
            row=row,
            webpage_url=webpage_url,
        ):
            worksheet.update_cell(row, Columns.status.value, status)
    except:
        worksheet.update_cell(row, Columns.status.value, "Error")
        raise
    else:
        worksheet.update_cell(row, Columns.status.value, "Done")


def process_source(
    request: DocExtractPage.RequestModel,
    row: int,
    webpage_url: str,
    worksheet,
) -> typing.Iterator[str | None]:
    audio_url = worksheet.cell(row, Columns.audio_url.value).value
    if not audio_url:
        yield "Downloading"
        if is_yt_url(webpage_url):
            audio_url, _ = download_youtube_to_wav(webpage_url)
        else:
            f = furl(webpage_url)
            if is_gdrive_url(f):
                doc_meta = doc_url_to_metadata(webpage_url)
                f_name = doc_meta.name
                worksheet.update_cell(row, Columns.title.value, f_name)
                f_bytes, _ = gdrive_download(f, doc_meta.mime_type)
                webpage_url = upload_file_from_bytes(
                    f_name, f_bytes, content_type=doc_meta.mime_type
                )
            audio_url, _ = audio_to_wav(webpage_url)
        worksheet.update_cell(row, Columns.audio_url.value, audio_url)

    transcript = worksheet.cell(row, Columns.transcript.value).value
    if not transcript:
        yield "Transcribing"
        transcript = run_asr(audio_url, request.selected_asr_model)
        worksheet.update_cell(row, Columns.transcript.value, transcript)

    if request.google_translate_target:
        translation = worksheet.cell(row, Columns.translation.value).value
        if not translation:
            yield "Translating"
            translation = Translate.run(
                texts=[transcript],
                target_language=request.google_translate_target,
                # source_language=request.language,
            )[0]
            worksheet.update_cell(row, Columns.translation.value, translation)
    else:
        translation = transcript
        worksheet.update_cell(row, Columns.translation.value, "")

    summary = worksheet.cell(row, Columns.summary.value).value
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
        worksheet.update_cell(row, Columns.summary.value, summary)


def is_yt_url(url: str) -> bool:
    return "youtube.com" in url or "youtu.be" in url


def get_worksheet(sheet_url, worksheet_index=0):
    from oauth2client.service_account import ServiceAccountCredentials
    import gspread

    # Authenticate with the Google Sheets API using a service account
    scope = [
        #     "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name(
        service_account_key_path, scope
    )
    client = gspread.authorize(creds)
    sheet = client.open_by_url(sheet_url)
    return sheet.get_worksheet(worksheet_index)

import json
import typing

import gspread
import yt_dlp
from oauth2client.service_account import ServiceAccountCredentials
from pydantic import BaseModel
from pytube import Playlist

import gooey_ui as st
from daras_ai_v2.asr import (
    google_translate_language_selector,
    AsrModels,
    run_asr,
    download_youtube_to_wav,
    run_google_translate,
)
from daras_ai_v2.base import BasePage
from daras_ai_v2.enum_selector_widget import enum_selector
from daras_ai_v2.functional import map_parallel
from daras_ai_v2.language_model import run_language_model, LargeLanguageModels
from daras_ai_v2.language_model_settings_widgets import language_model_settings
from daras_ai_v2.settings import service_account_key_path

ydl_opts = {
    "format": "m4a/bestaudio/best",
    # ℹ️ See help(yt_dlp.postprocessor) for a list of available Postprocessors and their arguments
    "postprocessors": [
        {  # Extract audio using ffmpeg
            "key": "FFmpegExtractAudio",
            "preferredcodec": "wav",
        }
    ],
}


class YoutubeBotPage(BasePage):
    title = "YouTube Transcripts + GPT extraction to Google Sheets"
    slug = "youtube-bot"
    slug_versions = ["YoutubeBot", "youtube-bot"]

    class RequestModel(BaseModel):
        youtube_urls: list[str] | None
        sheet_url: str | None
        task_instructions: str | None
        asr_selected_model: typing.Literal[tuple(e.name for e in AsrModels)] | None

        selected_model: typing.Literal[
            tuple(e.name for e in LargeLanguageModels)
        ] | None
        avoid_repetition: bool | None
        num_outputs: int | None
        quality: float | None
        max_tokens: int | None
        sampling_temperature: float | None

        language: str | None
        google_translate_target: str | None

    class ResponseModel(BaseModel):
        pass

    def render_form_v2(self):
        youtube_urls = st.session_state.get("youtube_urls") or []
        st.write(
            """
        #### 🤖 Youtube URLS
        """
        )
        text_value = st.text_area(
            "Enter a list of Youtube video URLs",
            label_visibility="collapsed",
            value="\n".join(youtube_urls),
            height=150,
        )
        st.session_state["youtube_urls"] = text_value.splitlines()
        sheet_url = st.text_input(
            "Enter a Google Sheet URL",
            key="sheet_url",
        )

    def validate_form_v2(self):
        assert st.session_state.get(
            "youtube_urls"
        ), "Please enter Youtube video URL/URLs"
        assert st.session_state.get("sheet_url"), "Please enter a Google Sheet URL"

    def preview_description(self, state: dict) -> str:
        return "Transcribe YouTube videos in any language with Whisper, Google Chirp & more, run your own GPT4 prompt on each transcript and save it all to a Google Sheet. Perfect for making a YouTube-based dataset to create your own chatbot or enterprise copilot (ie. just add the finished Google sheet url to the doc section in https://gooey.ai/copilot)."

    def render_results_v2(self, state: dict):
        pass

    def render_settings(self):
        st.text_area(
            "### 👩‍🏫 Task Instructions",
            key="task_instructions",
            height=100,
        )
        language_model_settings()
        enum_selector(AsrModels, label="###### ASR Model", key="asr_selected_model")
        st.write("---")
        google_translate_language_selector()
        st.write("---")
        # enum_selector(
        #     AsrOutputFormat, label="###### Output Format", key="output_format"
        # )

    def render_output(self):
        pass

    def authenticate(self):
        # # Authenticate with the Google Sheets API using a service account
        scope = [
            #     "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_name(
            service_account_key_path, scope
        )
        # import gspread

        client = gspread.authorize(creds)
        return client

    def get_worksheet(self, sheet_url, worksheet_index=0):
        client = self.authenticate()
        sheet = client.open_by_url(sheet_url)
        return sheet.get_worksheet(worksheet_index)

    def run(self, state: dict) -> typing.Iterator[str | None]:
        request: YoutubeBotPage.RequestModel = self.RequestModel.parse_obj(state)
        youtube_urls = request.youtube_urls
        video_urls = []
        for url in youtube_urls:
            try:
                playlist_video_urls = Playlist(url)
                video_urls.extend(playlist_video_urls)
            except KeyError:  # if the url is not a playlist
                video_urls.append(url)
        worksheet = self.get_worksheet(request.sheet_url)
        all_values = worksheet.get_all_values()
        if len(all_values) == 0:
            worksheet.append_row(
                [
                    "title",
                    "description",
                    "video_url",
                    "audio_url",
                    "transcript",
                    "translation",
                    "summary",
                    "status",
                ]
            )
        videos_in_sheet = [row[2] for row in all_values if row]
        new_urls = [url for url in video_urls if url not in videos_in_sheet]
        if new_urls:
            for url in new_urls:
                yield f"Adding videos {url}"
                worksheet.append_row(["", "", url, "", "", "", "", "0"])

        all_values = worksheet.get_all_values()
        yield f"Processing videos..."
        unprocessed_cells = [row for row in all_values if row[7] == "0"]
        if unprocessed_cells:
            unprocessed_videos = [cell[2] for cell in unprocessed_cells]
            map_parallel(
                lambda video_url: self.process_video(
                    video_url=video_url, worksheet=worksheet
                ),
                unprocessed_videos,
                max_workers=5,
            )

        yield f"Transcribing videos..."
        all_values = worksheet.get_all_values()
        unprocessed_cells = [row for row in all_values if row[7] == "1"]
        if unprocessed_cells:
            not_transcribed_videos = [(cell[2], cell[3]) for cell in unprocessed_cells]
            map_parallel(
                lambda url: self.transcribe_video(
                    video_url=url[0],
                    audio_url=url[1],
                    worksheet=worksheet,
                    language=request.language,
                    selected_model=request.asr_selected_model,
                ),
                not_transcribed_videos,
                max_workers=5,
            )

        yield f"Translating videos..."
        all_values = worksheet.get_all_values()
        unprocessed_cells = [row for row in all_values if row[7] == "2"]
        if unprocessed_cells:
            untranslated_videos = [(cell[4], cell[2]) for cell in unprocessed_cells]
            map_parallel(
                lambda arg: self.translate_video(
                    transcribed_text=arg[0],
                    video_url=arg[1],
                    worksheet=worksheet,
                    target_lang=request.google_translate_target,
                ),
                untranslated_videos,
                max_workers=5,
            )

        yield f"Extracting Facts..."
        all_values = worksheet.get_all_values()
        unprocessed_cells = [row for row in all_values if row[7] == "3"]
        if unprocessed_cells:
            not_summarised_videos = [(cell[5], cell[2]) for cell in unprocessed_cells]
            map_parallel(
                lambda arg: self.summarize(
                    translated_text=arg[0],
                    video_url=arg[1],
                    worksheet=worksheet,
                    request=request,
                ),
                not_summarised_videos,
                max_workers=5,
            )
        yield "Done"

    def process_video(self, video_url, worksheet):
        data = yt_dlp.YoutubeDL(ydl_opts).extract_info(video_url, download=False)
        json_data = json.loads(
            json.dumps(yt_dlp.YoutubeDL(ydl_opts).sanitize_info(data))
        )
        title = json_data["title"]
        description = json_data["description"]
        audio_url, size = download_youtube_to_wav(video_url)
        x = worksheet.find(video_url, case_sensitive=False)
        cell_list = worksheet.range(f"A{x.row}:H{x.row}")
        new_value = [title, description, video_url, audio_url, "", "", "", 1]
        for i, val in enumerate(new_value):  # gives us a tuple of an index and value
            cell_list[i].value = val
        worksheet.update_cells(cell_list)

    def transcribe_video(
        self, audio_url, video_url, worksheet, selected_model, language
    ):
        new_value = [run_asr(audio_url, selected_model, language)]
        new_value.extend(["", "", "2"])
        x = worksheet.find(video_url, case_sensitive=False)
        cell_list = worksheet.range(f"E{x.row}:H{x.row}")
        for i, val in enumerate(new_value):  # gives us a tuple of an index and value
            cell_list[i].value = val
        worksheet.update_cells(cell_list)

    def translate_video(self, transcribed_text, video_url, worksheet, target_lang="en"):
        x = worksheet.find(video_url, case_sensitive=False)
        new_value = run_google_translate(
            [transcribed_text],
            google_translate_target=target_lang,
        )
        new_value.extend(["", "3"])
        cell_list = worksheet.range(f"F{x.row}:H{x.row}")
        for i, val in enumerate(new_value):  # gives us a tuple of an index and value
            cell_list[i].value = val
        worksheet.update_cells(cell_list)

    #
    def summarize(self, translated_text, video_url, worksheet, request):
        x = worksheet.find(video_url, case_sensitive=False)
        prompt = request.task_instructions.strip() + "\n\n" + translated_text
        new_value = [
            "".join(
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
        ]
        new_value.extend(["4"])
        cell_list = worksheet.range(f"G{x.row}:H{x.row}")
        for i, val in enumerate(new_value):  # gives us a tuple of an index and value
            cell_list[i].value = val
        worksheet.update_cells(cell_list)

    def related_workflows(self) -> list:
        from recipes.asr import AsrPage
        from recipes.CompareLLM import CompareLLMPage
        from recipes.DocSearch import DocSearchPage
        from recipes.VideoBots import VideoBotsPage

        return [
            VideoBotsPage,
            AsrPage,
            CompareLLMPage,
            DocSearchPage,
        ]

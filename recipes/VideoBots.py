import collections
import re
import typing

import streamlit as st
from pydantic import BaseModel

from daras_ai.image_input import upload_file_from_bytes
from daras_ai_v2.base import BasePage
from daras_ai_v2.language_model import run_language_model
from daras_ai_v2.language_model_settings_widgets import language_model_settings
from daras_ai_v2.lipsync_settings_widgets import lipsync_settings
from daras_ai_v2.text_to_speech_settings_widgets import (
    TextToSpeechProviders,
    text_to_speech_settings,
)
from recipes.Lipsync import LipsyncPage
from recipes.TextToSpeech import TextToSpeechPage

BOT_SCRIPT_RE = re.compile(r"(\n)([\w\ ]+)(:)")


class VideoBotsPage(BasePage):
    title = "Create Interactive Video Bots"
    slug_versions = ["video-bots"]

    sane_defaults = {
        # tts
        "tts_provider": TextToSpeechProviders.GOOGLE_TTS.name,
        "google_voice_name": "en-IN-Wavenet-A",
        "google_pitch": 0.0,
        "google_speaking_rate": 1.0,
        "uberduck_voice_name": "kanye-west-rap",
        "uberduck_speaking_rate": 1.0,
        # gpt3
        "avoid_repetition": True,
        "num_outputs": 1,
        "quality": 1,
        "max_tokens": 1500,
        "sampling_temperature": 0.5,
        # wav2lip
        "face_padding_top": 0,
        "face_padding_bottom": 10,
        "face_padding_left": 0,
        "face_padding_right": 0,
    }

    class RequestModel(BaseModel):
        input_prompt: str
        bot_script: str | None
        input_face: str | None

        tts_provider: typing.Literal[
            tuple(e.name for e in TextToSpeechProviders)
        ] | None

        uberduck_voice_name: str | None
        uberduck_speaking_rate: float | None

        google_voice_name: str | None
        google_speaking_rate: float | None
        google_pitch: float | None

        avoid_repetition: bool | None
        num_outputs: int | None
        quality: float | None
        max_tokens: int | None
        sampling_temperature: float | None

        face_padding_top: int | None
        face_padding_bottom: int | None
        face_padding_left: int | None
        face_padding_right: int | None

    class ResponseModel(BaseModel):
        output_text: list[str]
        output_audio: list[str]
        output_video: list[str]
        final_prompt: str

    def preview_description(self, state: dict) -> str:
        return "Create an amazing, interactive AI videobot with just a GPT3 script + a video clip or photo. The host it on your own site or app."

    def render_description(self):
        st.write(
            """
        Have you ever wanted to create a character that you could talk to about anything? Ever wanted to create your own https://dara.network/RadBots? This is how. 

This workflow takes a dialog script describing your character (with some sample questions you expect folks to ask), a video clip of your character’s face and finally voice settings to build a videobot that anyone can speak to about anything and you can host directly in your own site or app. 

How It Works:
1. Appends the user's question to the bottom of your dialog script. 
2. Sends the appended script to OpenAI’s GPT3 asking it to respond to the question in the style of your character
3. Synthesizes your character's response as audio using your voice settings (using Google Text-To-Speech or Uberduck)
4. Lip syncs the face video clip to the voice clip
5. Shows the resulting video to the user

PS. This is the workflow that we used to create RadBots - a collection of Turing-test videobots, authored by leading international writers, singers and playwrights - and really inspired us to create Gooey.AI so that every person and organization could create their own fantastic characters, in any personality of their choosing.
        """
        )

    def render_form_v2(self):
        tab1, tab2 = st.tabs(["💬 Chat", "📝 Script"])
        with tab1:
            st.text_area(
                """
                Type in what you'd like to say to the bot
                """,
                key="input_prompt",
                height=50,
            )
        with tab2:
            st.text_area(
                """
                An example conversation with this bot
                """,
                key="bot_script",
                height=300,
            )
            st.file_uploader(
                """
                #### Input Face
                Upload a video/image that contains faces to use  
                *Recommended - mp4 / mov / png / jpg / gif* 
                """,
                key="face_file",
            )

    def validate_form_v2(self):
        assert st.session_state["input_prompt"], "Please type in a Messsage"
        assert st.session_state["bot_script"], "Please provide the Bot Script"

        face_file = st.session_state.get("face_file")
        input_face = st.session_state.get("input_face")
        assert face_file or input_face, "Please provide the Input Face"

        # upload input file
        if face_file:
            st.session_state["input_face"] = upload_file_from_bytes(
                face_file.name, face_file.getvalue()
            )

    def render_settings(self):
        text_to_speech_settings()
        language_model_settings()
        lipsync_settings()

    def render_example(self, state: dict):
        col1, col2 = st.columns(2)
        with col1:
            input_prompt = state.get("input_prompt")
            if input_prompt:
                st.write(
                    f"""
                    Question `{state.get('input_prompt', '')}`          
                    """
                )
        with col2:
            st.write("Response")
            output_video = state.get("output_video")
            if output_video:
                st.video(output_video[0])

    def render_output(self):
        st.write(f"Bot Responses")
        for idx, video_url in enumerate(st.session_state.get("output_video", [])):
            st.video(video_url)

    def render_steps(self):
        st.write("Input Face")
        st.video(st.session_state.get("input_face"))

        st.text_area(
            "Final Prompt",
            value=st.session_state.get("final_prompt"),
            height=200,
            disabled=True,
        )

        col1, col2 = st.columns(2)
        with col1:
            for idx, text in enumerate(st.session_state.get("output_text", [])):
                st.text_area(
                    f"Text Response {idx + 1}",
                    value=text,
                    disabled=True,
                )
        with col2:
            for idx, audio_url in enumerate(st.session_state.get("output_audio", [])):
                st.write(f"Generated Audio {idx + 1}")
                st.audio(audio_url)

    def run(self, state: dict) -> typing.Iterator[str | None]:
        request = self.RequestModel.parse_obj(state)

        all_names = [m.group(2) for m in BOT_SCRIPT_RE.finditer(request.bot_script)]
        common_names = collections.Counter(all_names).most_common()

        try:
            user_script_name, bot_script_name = (
                common_names[0][0].strip(),
                common_names[1][0].strip(),
            )
        except IndexError:
            user_script_name = "User"
            bot_script_name = "Bot"

        username = user_script_name
        current_user = st.session_state.get("_current_user")
        if current_user and current_user.display_name:
            username = current_user.display_name

        prompt = request.bot_script.strip()
        prompt = prompt.format(username=username)

        # user input -- User: <input>
        prompt += f"\n{user_script_name}: {request.input_prompt.strip()}"

        # completion prompt for openai -- Bot:
        prompt += f"\n{bot_script_name}:"

        state["final_prompt"] = prompt

        yield "Running GPT-3..."

        state["output_text"] = run_language_model(
            api_provider="openai",
            engine="text-davinci-003",
            quality=request.quality,
            num_outputs=request.num_outputs,
            temperature=request.sampling_temperature,
            prompt=prompt,
            max_tokens=request.max_tokens,
            stop=[f"{user_script_name}:", f"{bot_script_name}:"],
            avoid_repetition=request.avoid_repetition,
        )

        tts_state = dict(state)
        state["output_audio"] = []
        for text in state["output_text"]:
            tts_state["text_prompt"] = text
            yield from TextToSpeechPage().run(tts_state)
            state["output_audio"].append(tts_state["audio_url"])

        lip_state = dict(state)
        state["output_video"] = []
        for audio_url in state["output_audio"]:
            lip_state["input_audio"] = audio_url
            yield from LipsyncPage().run(lip_state)
            state["output_video"].append(lip_state["output_video"])

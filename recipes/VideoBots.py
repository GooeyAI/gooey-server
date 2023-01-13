import collections
import os
import re
import typing

import streamlit as st
from pydantic import BaseModel
from pathlib import Path

from daras_ai.image_input import upload_file_from_bytes, truncate_text
from daras_ai_v2.base import BasePage
from daras_ai_v2.hidden_html_widget import hidden_html_js
from daras_ai_v2.language_model import (
    run_language_model,
    GPT3_MAX_ALLOED_TOKENS,
    calc_gpt_tokens,
)
from daras_ai_v2.language_model_settings_widgets import language_model_settings
from daras_ai_v2.lipsync_settings_widgets import lipsync_settings
from daras_ai_v2.text_to_speech_settings_widgets import (
    TextToSpeechProviders,
    text_to_speech_settings,
)
from recipes.Lipsync import LipsyncPage
from recipes.TextToSpeech import TextToSpeechPage

BOT_SCRIPT_RE = re.compile(r"(\n)([\w\ ]+)(:)")
LANDBOT_URL_RE = re.compile(r"(\/)([A-z0-9]+\-[A-z0-9]+\-[A-z0-9]+)(\/)")


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

    def preview_image(self, state: dict) -> str | None:
        output_video = state.get("output_video")[0]
        filename_with_ext = os.path.basename(output_video)
        filename_without_ext = Path(output_video).resolve().stem
        return output_video.replace(
            filename_with_ext, f"thumbs/{filename_without_ext}.gif"
        )

    def preview_description(self, state: dict) -> str:
        return "Create an amazing, interactive AI videobot with just a GPT3 script + a video clip or photo. To host it on your own site or app, contact us at support@gooey.ai"

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
        st.text_area(
            """
            #### 👩‍💻 Prompt
            Ask me anything!
            """,
            key="input_prompt",
            help="What a fine day..",
            height=50,
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
        st.write("#### 📝 Script")
        st.text_area(
            """
            An example conversation with this bot
            """,
            key="bot_script",
            height=300,
        )
        st.file_uploader(
            """
            #### 👩‍🦰 Input Face
            Upload a video/image that contains faces to use  
            *Recommended - mp4 / mov / png / jpg / gif* 
            """,
            key="face_file",
        )

        st.write("---")

        text_to_speech_settings()
        st.write("---")
        language_model_settings()
        st.write("---")
        lipsync_settings()
        st.write("---")

        st.text_input("##### 🤖 Landbot URL", key="landbot_url")
        self.show_landbot_widget()

    def fields_to_save(self) -> [str]:
        return super().fields_to_save() + ["landbot_url"]

    def render_example(self, state: dict):
        input_prompt = state.get("input_prompt")
        if input_prompt:
            st.markdown("Prompt ```" + input_prompt.replace("\n", "") + "```")

        output_video = state.get("output_video")
        if output_video:
            st.video(output_video[0])

        output_text = state.get("output_text")
        if output_text:
            st.caption(truncate_text(output_text[0].replace("\n", ""), maxlen=200))

    def render_output(self):
        st.write(f"#### 💬 Response")
        for idx, output_text in enumerate(st.session_state.get("output_text", [])):
            try:
                output_video = st.session_state.get("output_video", [])[idx]
                st.video(output_video)
            except IndexError:
                pass
            st.caption(output_text.replace("\n", ""))

    def show_landbot_widget(self):
        landbot_url = st.session_state.get("landbot_url")
        if not landbot_url:
            return

        match = LANDBOT_URL_RE.search(landbot_url)
        if not match:
            return

        config_url = f"https://storage.googleapis.com/landbot.online/v3/{match.group(2)}/index.json"

        hidden_html_js(
            """
<script>
// destroy existing instance
if (top.myLandbot) {
    top.myLandbot.destroy();
}
// create new instance
top.myLandbot = new top.Landbot.Livechat({
    configUrl: %r,
});
</script>
            """
            % config_url
        )

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

        max_allowed_tokens = GPT3_MAX_ALLOED_TOKENS - calc_gpt_tokens(prompt)
        max_allowed_tokens = min(max_allowed_tokens, request.max_tokens)

        state["output_text"] = run_language_model(
            api_provider="openai",
            engine="text-davinci-003",
            quality=request.quality,
            num_outputs=request.num_outputs,
            temperature=request.sampling_temperature,
            prompt=prompt,
            max_tokens=max_allowed_tokens,
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

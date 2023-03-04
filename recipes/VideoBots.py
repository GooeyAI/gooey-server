import os
import os.path
import re
import typing

import streamlit as st
from furl import furl
from pydantic import BaseModel

from daras_ai.image_input import (
    truncate_text_words,
    upload_st_file,
)
from daras_ai_v2 import db
from daras_ai_v2.base import BasePage, MenuTabs
from daras_ai_v2.hidden_html_widget import hidden_html_js
from daras_ai_v2.language_model import (
    run_language_model,
    GPT3_MAX_ALLOED_TOKENS,
    calc_gpt_tokens,
    ConversationEntry,
    run_chatgpt,
    format_chatml_message,
    CHATML_END_TOKEN,
    CHATML_START_TOKEN,
    LargeLanguageModels,
    CHATML_ROLE_ASSISSTANT,
    CHATML_ROLE_USER,
    CHATML_ROLE_SYSTEM,
)
from daras_ai_v2.language_model_settings_widgets import language_model_settings
from daras_ai_v2.lipsync_settings_widgets import lipsync_settings
from daras_ai_v2.text_to_speech_settings_widgets import (
    TextToSpeechProviders,
    text_to_speech_settings,
)
from recipes.Lipsync import LipsyncPage
from recipes.TextToSpeech import TextToSpeechPage
from routers.facebook import get_page_display_name, ig_connect_url, fb_connect_url

BOT_SCRIPT_RE = re.compile(
    # start of line
    r"^"
    # name of bot / user
    r"([\w\ \t]+)"
    # colon
    r"\:\ ",
    flags=re.M,
)


class VideoBotsPage(BasePage):
    title = "Create Interactive Video Bots"
    slug_versions = ["video-bots"]

    sane_defaults = {
        "messages": [],
        # tts
        "tts_provider": TextToSpeechProviders.GOOGLE_TTS.name,
        "google_voice_name": "en-IN-Wavenet-A",
        "google_pitch": 0.0,
        "google_speaking_rate": 1.0,
        "uberduck_voice_name": "hecko",
        "uberduck_speaking_rate": 1.0,
        # gpt3
        "selected_model": LargeLanguageModels.gpt_3_5_turbo.name,
        "avoid_repetition": True,
        "num_outputs": 1,
        "quality": 1.0,
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

        selected_model: typing.Literal[
            tuple(e.name for e in LargeLanguageModels)
        ] | None
        avoid_repetition: bool | None
        num_outputs: int | None
        quality: float | None
        max_tokens: int | None
        sampling_temperature: float | None

        face_padding_top: int | None
        face_padding_bottom: int | None
        face_padding_left: int | None
        face_padding_right: int | None

        messages: list[ConversationEntry] | None

    class ResponseModel(BaseModel):
        output_text: list[str]
        output_audio: list[str]
        output_video: list[str]
        final_prompt: str

    def related_workflows(self):
        from recipes.LipsyncTTS import LipsyncTTSPage
        from recipes.CompareText2Img import CompareText2ImgPage
        from recipes.DeforumSD import DeforumSDPage

        return [
            LipsyncTTSPage,
            DeforumSDPage,
            TextToSpeechPage,
            CompareText2ImgPage,
        ]

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
        # assert st.session_state["input_prompt"], "Please type in a Messsage"
        # assert st.session_state["bot_script"], "Please provide the Bot Script"

        face_file = st.session_state.get("face_file")
        if face_file:
            st.session_state["input_face"] = upload_st_file(face_file)
        # assert st.session_state.get("input_face"), "Please provide the Input Face"

    def render_settings(self):
        st.text_area(
            """
            ##### 📝 Script
            A brief description of the bot, and an example conversation (~1000 words)
            """,
            key="bot_script",
            height=300,
        )
        st.write("---")

        if not "__enable_audio" in st.session_state:
            st.session_state["__enable_audio"] = bool(
                st.session_state.get("tts_provider")
            )
        enable_audio = st.checkbox("Enable Audio?", key="__enable_audio")
        if not enable_audio:
            st.session_state["tts_provider"] = None
        else:
            text_to_speech_settings()
            st.write("---")

            if not "__enable_video" in st.session_state:
                st.session_state["__enable_video"] = bool(
                    st.session_state.get("input_face")
                )
            enable_video = st.checkbox("Enable Video?", key="__enable_video")
            if not enable_video:
                st.session_state["input_face"] = None
            else:
                st.file_uploader(
                    """
                    #### 👩‍🦰 Input Face
                    Upload a video/image that contains faces to use  
                    *Recommended - mp4 / mov / png / jpg / gif* 
                    """,
                    key="face_file",
                    upload_key="input_face",
                )
                st.write("---")

                lipsync_settings()
                st.write("---")

        language_model_settings()
        st.write("---")

        st.text_input("##### 🤖 Landbot URL", key="landbot_url")
        self.show_landbot_widget()

    def fields_to_save(self) -> [str]:
        return super().fields_to_save() + ["landbot_url"]

    def render_example(self, state: dict):
        input_prompt = state.get("input_prompt")
        if input_prompt:
            st.write(
                "**Prompt**\n```properties\n"
                + truncate_text_words(input_prompt, maxlen=200)
                + "\n```"
            )

        st.write("**Response**")

        output_video = state.get("output_video")
        if output_video:
            st.video(output_video[0])

        output_text = state.get("output_text")
        if output_text:
            st.write(truncate_text_words(output_text[0], maxlen=200))

    def _render_before_output(self):
        super()._render_before_output()
        if st.session_state.get("messages") and st.button("🗑️ Clear History"):
            st.session_state["messages"].clear()

    def render_output(self):
        messages = st.session_state.get("messages", [])
        output_text = st.session_state.get("output_text", [])
        if messages:
            st.write(f"#### 💬 Conversation")
            st.caption(
                "\n\n".join(
                    [
                        f'**_{(entry.get("display_name") or entry["role"]).capitalize()}_**\\\n{entry["content"]}'
                        for entry in messages[:-1]
                    ]
                )
            )
            last_msg = messages[-1]
            bot_name = f'**_{(last_msg.get("display_name") or last_msg["role"]).capitalize()}_**\\\n'
        elif output_text:
            st.write(f"#### 💌 Response")
            bot_name = ""
        else:
            return
        for idx, text in enumerate(output_text):
            try:
                output_video = st.session_state.get("output_video", [])[idx]
                st.video(output_video)
            except IndexError:
                pass
            st.write(bot_name + text)

    def show_landbot_widget(self):
        landbot_url = st.session_state.get("landbot_url")
        if not landbot_url:
            return

        f = furl(landbot_url)
        config_path = os.path.join(f.host, *f.path.segments[:2])
        config_url = f"https://storage.googleapis.com/{config_path}/index.json"

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
        if st.session_state.get("tts_provider"):
            st.video(st.session_state.get("input_face"), caption="Input Face")

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
        request: VideoBotsPage.RequestModel = self.RequestModel.parse_obj(state)
        use_chatgpt = request.selected_model == LargeLanguageModels.gpt_3_5_turbo.name

        user_input = request.input_prompt.strip()
        if not user_input:
            return

        bot_script = request.bot_script
        script_matches = list(BOT_SCRIPT_RE.finditer(bot_script))
        scripted_msgs = []
        # extract messages from script
        for idx in range(len(script_matches)):
            match = script_matches[idx]
            try:
                next_match = script_matches[idx + 1]
            except IndexError:
                next_match_start = None
            else:
                next_match_start = next_match.start()
            if (len(script_matches) - idx) % 2 == 0:
                role = CHATML_ROLE_USER
            else:
                role = CHATML_ROLE_ASSISSTANT
            scripted_msgs.append(
                {
                    "role": role,
                    "display_name": match.group(1).strip(),
                    "content": bot_script[match.end() : next_match_start].strip(),
                }
            )

        # get user/bot display names
        try:
            bot_display_name = scripted_msgs[-1]["display_name"]
        except IndexError:
            bot_display_name = CHATML_ROLE_ASSISSTANT
        try:
            user_display_name = scripted_msgs[-2]["display_name"]
        except IndexError:
            user_display_name = CHATML_ROLE_USER

        # extract system message from script
        system_message = bot_script
        if script_matches:
            system_message = system_message[: script_matches[0].start()]
        # add the system message
        system_message = system_message.strip()
        if system_message:
            # replace current user's name
            current_user = st.session_state.get("_current_user")
            if current_user and current_user.display_name:
                system_message = system_message.format(
                    username=current_user.display_name
                )
            # insert to top
            scripted_msgs.insert(
                0, {"role": CHATML_ROLE_SYSTEM, "content": system_message}
            )

        st.session_state["messages"] = saved_msgs = request.messages

        # add user input to conversation
        saved_msgs.append(
            {
                "role": CHATML_ROLE_USER,
                "display_name": user_display_name,
                "content": user_input,
            }
        )

        if not use_chatgpt:
            # assistant prompt to triger a model response
            saved_msgs.append(
                {
                    "role": CHATML_ROLE_ASSISSTANT,
                    "display_name": bot_display_name,
                    "content": "",
                }
            )

        # add the entire conversation to the prompt
        all_messages = scripted_msgs + saved_msgs
        prompt = "\n".join(format_chatml_message(entry) for entry in all_messages)
        state["final_prompt"] = prompt
        # ensure input script is not too big
        max_allowed_tokens = GPT3_MAX_ALLOED_TOKENS - calc_gpt_tokens(prompt)
        max_allowed_tokens = min(max_allowed_tokens, request.max_tokens)
        if max_allowed_tokens < 0:
            raise ValueError("Input Script is too long! Please reduce the script size.")

        if use_chatgpt:
            yield "Running ChatGPT..."
            output_messages = run_chatgpt(
                messages=[
                    {"role": s["role"], "content": s["content"]} for s in all_messages
                ],
                max_tokens=max_allowed_tokens,
                # quality=request.quality,
                num_outputs=request.num_outputs,
                temperature=request.sampling_temperature,
                avoid_repetition=request.avoid_repetition,
            )
            # save model response
            saved_msgs.append(
                {
                    "role": CHATML_ROLE_ASSISSTANT,
                    "display_name": bot_display_name,
                    "content": output_messages[0]["content"],
                }
            )
            state["output_text"] = [entry["content"] for entry in output_messages]
        else:
            # assistant prompt to triger a model response
            yield f"Running GPT-3..."
            state["output_text"] = run_language_model(
                model=request.selected_model,
                quality=request.quality,
                num_outputs=request.num_outputs,
                temperature=request.sampling_temperature,
                prompt=prompt,
                max_tokens=max_allowed_tokens,
                stop=[CHATML_END_TOKEN, CHATML_START_TOKEN],
                avoid_repetition=request.avoid_repetition,
            )
            # save model response
            saved_msgs[-1]["content"] = state["output_text"][0]

        state["output_audio"] = []
        state["output_video"] = []

        if not request.tts_provider:
            return
        tts_state = dict(state)
        for text in state["output_text"]:
            tts_state["text_prompt"] = text
            yield from TextToSpeechPage().run(tts_state)
            state["output_audio"].append(tts_state["audio_url"])

        if not request.input_face:
            return
        lip_state = dict(state)
        for audio_url in state["output_audio"]:
            lip_state["input_audio"] = audio_url
            yield from LipsyncPage().run(lip_state)
            state["output_video"].append(lip_state["output_video"])

    def get_tabs(self):
        tabs = super().get_tabs()
        tabs.extend([MenuTabs.integrations])
        return tabs

    def render_selected_tab(self, selected_tab):
        super().render_selected_tab(selected_tab)

        if selected_tab != MenuTabs.integrations:
            return

        user = st.session_state.get("_current_user")
        if not user or hasattr(user, "_is_anonymous"):
            st.write(
                "**Please Login to connect this workflow to Your Website, Instagram, Whatsapp & More**"
            )
            return

        st.write("### Messenger Bot")

        st.markdown(
            f"""
            <!--
            <div style='height: 50px'>
                <a target="_blank" class="streamlit-like-btn" href="{ig_connect_url}">
                  <img height="20" src="https://www.instagram.com/favicon.ico">️
                  &nbsp; 
                  Add Your Instagram Page
                </a>
            </div>
            -->
            <div style='height: 50px'>
                <a target="_blank" class="streamlit-like-btn" href="{fb_connect_url}">
                  <img height="20" src="https://www.facebook.com/favicon.ico">️             
                  &nbsp; 
                  Add Your Facebook Page
                </a>
            </div>
            """,
            unsafe_allow_html=True,
        )

        fb_pages = st.session_state.get("__fb_pages")
        if "__fb_pages" not in st.session_state:
            with st.spinner("Loading Facebook Pages..."):
                fb_pages = (
                    db.get_collection_ref(db.FB_PAGES_COLLECTION)
                    .where("uid", "==", user.uid)
                    .get()
                )
            st.session_state["__fb_pages"] = fb_pages
        st.write("Please reload this page after logging in.")

        if not fb_pages:
            return

        st.write("##### Select Pages to Connect")
        selected_pages = {}

        page_slug = self.slug_versions[0]
        query_params = dict(self._get_current_api_url().query.params)

        for snapshot in fb_pages:
            fb_page = snapshot.to_dict()
            is_connected = (
                fb_page.get("connected_page_slug") == self.slug_versions[0]
                and fb_page.get("connected_query_params") == query_params
            )
            selected = st.checkbox(get_page_display_name(fb_page), value=is_connected)
            selected_pages[snapshot.id] = (snapshot, selected)

        if selected_pages and st.button("🖇️ Connect"):
            with st.spinner("Connecting..."):
                for snapshot, selected in selected_pages.values():
                    if selected:
                        update = {
                            "connected_page_slug": page_slug,
                            "connected_query_params": query_params,
                        }
                    else:
                        update = {
                            "connected_page_slug": None,
                            "connected_query_params": {},
                        }
                    snapshot.reference.update(update)
            st.success("Done ✅")

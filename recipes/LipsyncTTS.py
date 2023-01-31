import typing

import streamlit as st
from pydantic import BaseModel

from daras_ai.image_input import upload_file_from_bytes
from recipes.Lipsync import LipsyncPage
from recipes.TextToSpeech import TextToSpeechPage


class LipsyncTTSPage(LipsyncPage, TextToSpeechPage):
    title = "Lipsync Video with Any Text"
    slug_versions = ["LipsyncTTS", "lipsync-maker"]

    class RequestModel(BaseModel):
        input_face: str
        input_audio: str | None

        face_padding_top: int | None
        face_padding_bottom: int | None
        face_padding_left: int | None
        face_padding_right: int | None

        text_prompt: str

        tts_provider: str | None

        uberduck_voice_name: str | None
        uberduck_speaking_rate: float | None

        google_voice_name: str | None
        google_speaking_rate: float | None
        google_pitch: float | None

    class ResponseModel(BaseModel):
        output_video: str

    def render_form(self) -> bool:
        with st.form("my_form"):
            face_file = st.file_uploader(
                """
                #### Input Face
                Upload a video/image that contains faces to use
                *Recommended - mp4 / mov / png / jpg*
                """,
            )

            text_prompt = st.text_area(
                """
                #### Input Text
                This generates audio for your video
                """,
                key="text_prompt",
                placeholder="This is a test",
            )
            submitted = st.form_submit_button("🏃‍ Submit")

        # upload input files if submitted
        if submitted:
            if not text_prompt:
                st.error("Text input cannot be empty", icon="⚠️")
                return False
            if not face_file:
                if "input_face" not in st.session_state:
                    st.error("Input face cannot be empty", icon="⚠️")
                    return False

            with st.spinner("Uploading..."):
                if face_file:
                    st.session_state["input_face"] = upload_file_from_bytes(
                        face_file.name,
                        face_file.getvalue(),
                        content_type=face_file.type,
                    )

        return submitted

    def preview_description(self, state: dict) -> str:
        return "Add your text prompt, pick a voice & upload a sample video to quickly create realistic lipsync videos. Discover the ease of text-to-video AI."

    def render_description(self):
        st.write(
            """
                This recipe takes any text and a video of a person (plus the voice defined in Settings) to create a lipsync'd video of that person speaking your text.

                How It Works:

                1. Takes any text + a video (with a face in it)
                2. Generates audio file in voice of your choice
                3. Merges the audio and video
                4. Renders a lipsynced video with your text
            """
        )

    def render_settings(self):
        LipsyncPage.render_settings(self)
        TextToSpeechPage.render_settings(self)

    def run(self, state: dict) -> typing.Iterator[str | None]:
        yield from TextToSpeechPage.run(self, state)
        # IMP: Copy output of TextToSpeechPage "audio_url" to Lipsync as "input_audio"
        state["input_audio"] = state["audio_url"]
        yield from LipsyncPage.run(self, state)

    def render_example(self, state: dict):
        col1, col2 = st.columns(2)

        with col1:
            input_text = state.get("text_prompt")
            if input_text:
                st.write("**Input Text**")
                st.write(input_text)
            else:
                st.empty()

            # input_audio = state.get("input_audio")
            # if input_audio:
            #    st.write("Synthesized Voice")
            #    st.audio(input_audio)
            # else:
            #    st.empty()

            input_face = state.get("input_face")
            if not input_face:
                st.empty()
            elif input_face.endswith(".mp4") or input_face.endswith(".mov"):
                st.video(input_face, caption="Input Face (Video)")
            else:
                st.image(input_face, caption="Input Face (Image)")

        with col2:
            output_video = state.get("output_video")
            if output_video:
                st.video(output_video, caption="Output Video")
            else:
                st.empty()

    def render_output(self):
        self.render_example(st.session_state)


if __name__ == "__main__":
    LipsyncTTSPage().render()

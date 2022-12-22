from enum import Enum

import streamlit as st

from daras_ai_v2.enum_selector_widget import enum_selector


class TextToSpeechProviders(Enum):
    GOOGLE_TTS = "Google Cloud Text-to-Speech"
    UBERDUCK = "uberduck.ai"


def text_to_speech_settings():
    st.write(
        """
        #### Voice Settings
        """
    )

    tts_provider = enum_selector(
        TextToSpeechProviders,
        "###### Speech Provider",
        key="tts_provider",
    )

    match tts_provider:
        case TextToSpeechProviders.GOOGLE_TTS.name:
            st.write(
                "*Please refer to the list of voice names [here](https://cloud.google.com/text-to-speech/docs/voices)*"
            )
            col1, col2 = st.columns(2)
            with col1:
                st.text_input(
                    label="""
                    ###### Voice name (Google TTS)
                    """,
                    key="google_voice_name",
                )

            col1, col2 = st.columns(2)
            with col1:
                st.slider(
                    """
                    ###### Speaking rate 
                    *`1.0` is the normal native speed of the speaker*
                    """,
                    min_value=0.25,
                    max_value=4.0,
                    step=0.1,
                    key="google_speaking_rate",
                )
            with col2:
                st.slider(
                    """
                    ###### Pitch
                    *Increase/Decrease semitones from the original pitch*
                    """,
                    min_value=-20.0,
                    max_value=20.0,
                    step=0.25,
                    key="google_pitch",
                )

        case TextToSpeechProviders.UBERDUCK.name:
            st.write(
                "*Please refer to the list of voice names [here](https://app.uberduck.ai/leaderboard/voice)*"
            )
            col1, col2 = st.columns(2)
            with col1:
                st.text_input(
                    label="""
                    ###### Voice name (Uberduck)
                    """,
                    key="uberduck_voice_name",
                )
                st.slider(
                    """
                    ###### Speaking rate 
                    *`1.0` is the normal native speed of the speaker*
                    """,
                    min_value=0.5,
                    max_value=3.0,
                    step=0.25,
                    key="uberduck_speaking_rate",
                )

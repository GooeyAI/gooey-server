import streamlit as st

from daras_ai_v2.stable_diffusion import Text2ImgModels, InpaintingModels


def negative_prompt_setting(selected_model: str = None):
    if selected_model in [Text2ImgModels.dall_e.name, InpaintingModels.runway_ml.name]:
        return

    st.text_area(
        """
        #### Negative Prompt
        This allows you to specify what you DON'T want to see. 
        Useful negative prompts can be found [here](https://www.youtube.com/watch?v=cWZsizoAwT4).
        """,
        key="negative_prompt",
    )

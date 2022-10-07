import random

import replicate
import requests

from daras_ai.core import daras_ai_step_config, var_selector
import streamlit as st


@daras_ai_step_config("Text to Img")
def text_to_img(idx, variables, state):
    st.write("### Config")

    selected_model = st.selectbox(
        "Model",
        options=["Stable Diffusion"],
    )
    state.update({"selected_model": selected_model})

    num_outputs = int(
        st.number_input("# of outputs", value=int(state.get("num_outputs", 4)), step=1)
    )
    state.update({"num_outputs": num_outputs})

    st.write("### Input")

    input_var = st.text_input(
        "Input var",
        help=f"Text to Img Input {idx}",
        value=state.get("input_var", ""),
    )
    state.update({"input_var": input_var})

    st.write("### Output")

    output_var = st.text_input(
        "Output var",
        help=f"Text to Img Output {idx}",
        value=state.get("output_var", ""),
    )
    state.update({"input_var": output_var})


# def dall_e(prompt):
#     requests.post(
#         "https://labs.openai.com/api/labs/tasks",
#         headers={
#             "authorization": f"Bearer sess-OHLA4SjHeAylHVI8AUtToUO6Wz5sg7EFOAbAvcMd",
#         },
#         json={"task_type": "text2im", "prompt": {"caption": prompt, "batch_size": 4}},
#     )

import random

import replicate
import requests

from daras_ai.core import daras_ai_step_config, var_selector, daras_ai_step_computer
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
    state.update({"output_var": output_var})


@daras_ai_step_computer
def text_to_img(idx, variables, state):
    input_var = state["input_var"]
    output_var = state["output_var"]
    selected_model = state["selected_model"]
    num_outputs = state["num_outputs"]

    prompt = variables[input_var]

    if not (prompt and output_var):
        return

    if isinstance(prompt, list):
        prompt = random.choice(prompt)

    match selected_model:
        case "Stable Diffusion":
            model = replicate.models.get("stability-ai/stable-diffusion")
            photos = model.predict(prompt=prompt, num_outputs=num_outputs)
            variables[output_var] = photos


# def dall_e(prompt):
#     requests.post(
#         "https://labs.openai.com/api/labs/tasks",
#         headers={
#             "authorization": f"Bearer sess-OHLA4SjHeAylHVI8AUtToUO6Wz5sg7EFOAbAvcMd",
#         },
#         json={"task_type": "text2im", "prompt": {"caption": prompt, "batch_size": 4}},
#     )

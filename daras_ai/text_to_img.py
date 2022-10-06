import replicate
import requests

from daras_ai.core import daras_ai_step, var_selector
import streamlit as st


@daras_ai_step("Text to Img")
def text_to_img(idx, variables, state):
    selected_model = st.selectbox(
        "Model",
        options=["Stable Diffusion"],
    )

    model_input_var = var_selector(
        "Input var",
        help=f"Text to Img Input {idx}",
        state=state,
        variables=variables,
    )
    model_output_var = var_selector(
        "Output var",
        help=f"Text to Img Output {idx}",
        state=state,
        variables=variables,
    )

    if not (model_input_var and model_output_var):
        return

    match selected_model:
        case "Stable Diffusion":
            variables[model_output_var] = stable_diffusion(variables[model_input_var])


@st.cache
def stable_diffusion(prompt):
    model = replicate.models.get("stability-ai/stable-diffusion")
    photo = model.predict(prompt=prompt)[0]
    return photo


# def dall_e(prompt):
#     requests.post(
#         "https://labs.openai.com/api/labs/tasks",
#         headers={
#             "authorization": f"Bearer sess-OHLA4SjHeAylHVI8AUtToUO6Wz5sg7EFOAbAvcMd",
#         },
#         json={"task_type": "text2im", "prompt": {"caption": prompt, "batch_size": 4}},
#     )

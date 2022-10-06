import replicate
import requests

from daras_ai.core import daras_ai_step, var_selector
import streamlit as st


@daras_ai_step("Text to Img")
def text_to_img(idx, variables, state):
    st.write("### Config")

    selected_model = st.selectbox(
        "Model",
        options=["Stable Diffusion"],
    )

    num_outputs = int(
        st.number_input("# of outputs", value=int(state.get("num_outputs", 4)), step=1)
    )
    state.update({"num_outputs": num_outputs})

    st.write("### Input")

    model_input_var = var_selector(
        "Input var",
        help=f"Text to Img Input {idx}",
        state=state,
        variables=variables,
    )

    st.write("### Output")

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
            variables[model_output_var] = stable_diffusion(
                variables[model_input_var],
                num_outputs,
            )


@st.cache
def stable_diffusion(prompt, num_outputs):
    model = replicate.models.get("stability-ai/stable-diffusion")
    photos = model.predict(prompt=prompt, num_outputs=num_outputs)
    return photos


# def dall_e(prompt):
#     requests.post(
#         "https://labs.openai.com/api/labs/tasks",
#         headers={
#             "authorization": f"Bearer sess-OHLA4SjHeAylHVI8AUtToUO6Wz5sg7EFOAbAvcMd",
#         },
#         json={"task_type": "text2im", "prompt": {"caption": prompt, "batch_size": 4}},
#     )

import random

import replicate
import streamlit as st


from daras_ai.core import daras_ai_step_config, daras_ai_step_computer


@daras_ai_step_config("Img to Img")
def img_to_img(idx, variables, state):
    st.write("### Config")

    selected_model = st.selectbox(
        "Model",
        options=["Stable Diffusion"],
        help=f"Selected Model {idx}",
    )
    state.update({"selected_model": selected_model})

    num_outputs = int(
        st.number_input("# of outputs", value=int(state.get("num_outputs", 4)), step=1)
    )
    state.update({"num_outputs": num_outputs})

    num_inference_steps = int(
        st.number_input(
            "# of inference steps",
            value=int(state.get("num_inference_steps", 100)),
            step=1,
        )
    )
    state.update({"num_inference_steps": num_inference_steps})

    st.write("### Input")

    text_input_var = st.text_input(
        "Text Input Variable",
        help=f"Text Input Variable {idx}",
        value=state.get("text_input_var", ""),
    )
    state.update({"text_input_var": text_input_var})

    img_input_var = st.text_input(
        "Init Image Input Variable",
        help=f"Init Image Input Varialbe {idx}",
        value=state.get("img_input_var", ""),
    )
    state.update({"img_input_var": img_input_var})

    mask_img_input_var = st.text_input(
        "Mask Image Input Variable (optional)",
        help=f"Mask Image Input Variable {idx}",
        value=state.get("mask_img_input_var", ""),
    )
    state.update({"mask_img_input_var": mask_img_input_var})

    st.write("### Output")

    output_var = st.text_input(
        "Output var",
        help=f"Img to Img Output {idx}",
        value=state.get("output_var", ""),
    )
    state.update({"output_var": output_var})


@daras_ai_step_computer
def img_to_img(idx, variables, state):
    text_input_var = state["text_input_var"]
    img_input_var = state["img_input_var"]
    mask_img_input_var = state["mask_img_input_var"]
    output_var = state["output_var"]
    selected_model = state["selected_model"]
    num_outputs = state["num_outputs"]
    num_inference_steps = state["num_inference_steps"]

    prompt = variables.get(text_input_var)
    init_img = variables.get(img_input_var)
    mask_img = variables.get(mask_img_input_var)

    if not (prompt and output_var and init_img):
        return

    if isinstance(prompt, list):
        prompt = random.choice(prompt)

    match selected_model:
        case "Stable Diffusion":
            model = replicate.models.get("devxpy/glid-3-xl-stable").versions.get(
                "cef7ec313a60334cd1d52aef39118ae9df4f44987899107b43d15472e5b3d504"
            )
            params = dict(
                prompt=prompt,
                num_outputs=num_outputs,
                edit_image=init_img,
                mask=mask_img,
                num_inference_steps=num_inference_steps,
            )
            variables[output_var] = model.predict(**params)


# def dall_e(prompt):
#     requests.post(
#         "https://labs.openai.com/api/labs/tasks",
#         headers={
#             "authorization": f"Bearer sess-OHLA4SjHeAylHVI8AUtToUO6Wz5sg7EFOAbAvcMd",
#         },
#         json={"task_type": "text2im", "prompt": {"caption": prompt, "batch_size": 4}},
#     )

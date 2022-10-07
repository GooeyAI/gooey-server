import json

import streamlit as st

from daras_ai.core import daras_ai_step_config, daras_ai_step_computer


@daras_ai_step_config("Text Training Data")
def text_train_data(idx, variables, state):
    training_data = json.loads(state.get("training_data", "null"))

    st.write("### Config")

    add = st.button("Add an example", help="Add an example")
    if not training_data:
        training_data = []
        add = True

    if add:
        training_data.append({"prompt": "", "completion": ""})
        state.update({"training_data": json.dumps(training_data)})

    for idx, eg in enumerate(training_data):
        col1, col2 = st.columns([1, 5])
        with col1:
            delete = st.button(f"🗑 ({idx + 1})", help=f"Delete example ({idx + 1})")
            if delete:
                training_data.pop(idx)
                state.update({"training_data": json.dumps(training_data)})
                st.experimental_rerun()
                return
        with col2:
            eg["prompt"] = st.text_area(
                f"Prompt ({idx + 1})",
                value=eg["prompt"],
            )
            eg["completion"] = st.text_area(
                f"Completion ({idx + 1})",
                value=eg["completion"],
            )
        state.update({"training_data": json.dumps(training_data)})

    st.write("### Output")

    out_var = st.text_input(
        "Training Data Variable",
        help=f"Text Train Data Varialbe {idx}",
        value=state.get("out_var", ""),
    )
    if not out_var:
        return
    state.update({"out_var": out_var})

    st.write("Training Data Value")
    st.dataframe(training_data)


@daras_ai_step_computer
def text_train_data(idx, variables, state):
    training_data_json = state["training_data"]
    output_var = state["out_var"]

    if not (training_data_json and output_var):
        raise ValueError

    variables[output_var] = json.loads(training_data_json)

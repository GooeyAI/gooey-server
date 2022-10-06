import json

import streamlit as st

from daras_ai.core import daras_ai_step


@daras_ai_step("Text Training Data")
def text_train_data(idx, variables, state):
    training_data = json.loads(state.get("training_data", "null"))

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

    st.write("### Input")

    st.write("**Training data**")
    st.dataframe(training_data)

    st.write("### Output")

    out_var = st.text_input(
        label="Training Output var",
        value=state.get("out_var", ""),
    )
    if not out_var:
        return
    state.update({"out_var": out_var})
    variables[out_var] = training_data

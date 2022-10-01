import ast
import json

import parse
import streamlit as st
from glom import glom
from html2text import html2text

from daras_ai.components.core import daras_ai_step

import streamlit_nested_layout


@daras_ai_step("Text Training Data")
def text_train_data(variables, state, set_state):
    training_data = json.loads(state.get("training_data", "null"))

    add = st.button("Add", help="Add an example")
    if not training_data:
        training_data = []
        add = True

    if add:
        training_data.append({"prompt": "", "completion": ""})
        set_state({"training_data": json.dumps(training_data)})

    for idx, eg in enumerate(training_data):
        col1, col2, col3 = st.columns(3)
        with col1:
            eg["prompt"] = st.text_area(
                f"Prompt ({idx + 1})",
                value=eg["prompt"],
            )
        with col2:
            eg["completion"] = st.text_area(
                f"Completion ({idx + 1})",
                value=eg["completion"],
            )
        with col3:
            delete = st.button(f"🗑", help=f"Delete example ({idx + 1})")
            if delete:
                training_data.pop(idx)
                set_state({"training_data": json.dumps(training_data)})
                st.experimental_rerun()
                return
        set_state({"training_data": json.dumps(training_data)})

    st.write("**Training data**")
    st.dataframe(training_data)

    out_var = st.text_input(
        label="Training Output var",
        value=state.get("out_var"),
    )
    if out_var is not None:
        set_state({"out_var": out_var})
        variables[out_var] = training_data

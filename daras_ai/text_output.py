import gooey_ui as st

from daras_ai.core import daras_ai_step_config, daras_ai_step_io


@daras_ai_step_config("Text Output", is_output=True, is_expanded=True)
def raw_text_output(idx, variables, state):
    var_name = st.text_input(
        "Variable Name",
        value=state.get("var_name", "text_output"),
        help=f"Text Output name {idx}",
    )
    state.update({"var_name": var_name})


@daras_ai_step_io
def raw_text_output(idx, variables, state):
    var_name = state.get("var_name", "")
    if not var_name:
        return
    if var_name not in variables:
        variables[var_name] = ""

    text_list = variables[var_name]
    if not isinstance(text_list, list):
        text_list = [text_list]

    st.write(var_name)

    for j, text in enumerate(text_list):
        st.text_area(
            f"{var_name} ({j + 1})",
            help=f"Output value {idx + 1}, {j + 1}",
            value=text,
            disabled=True,
            height=200,
        )

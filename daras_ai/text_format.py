import ast
import parse
import streamlit as st
from glom import glom
from html2text import html2text

from daras_ai.core import daras_ai_step_config, daras_ai_step_computer
from daras_ai.train_data_formatter import input_spec_parse_pattern


@daras_ai_step_config("Text formatter")
def text_format(idx, variables, state):
    format_str = st.text_area(
        "Format String", help=f"Format String {idx}", value=state.get("format_str", "")
    )
    state.update({"format_str": format_str})

    output_var = st.text_input(
        "Output variable",
        help=f"Output ID {idx}",
        value=state.get("output_var", ""),
    )
    state.update({"output_var": output_var})

    st.text_area(
        "Output value (generated)", value=variables.get(output_var, ""), disabled=True
    )


@daras_ai_step_computer
def text_format(idx, variables, state):
    format_str = state["format_str"]
    output_var = state["output_var"]

    if not output_var:
        raise ValueError

    variables[output_var] = daras_ai_format_str(format_str, variables)


def daras_ai_format_str(format_str, variables):
    input_spec_results: list[parse.Result] = list(
        parse.findall(input_spec_parse_pattern, format_str)
    )
    for spec_result in input_spec_results:
        spec = spec_result.fixed[0]
        variable_value = glom(variables, ast.literal_eval(spec))
        format_str = format_str.replace("{{" + spec + "}}", variable_value)
    return format_str

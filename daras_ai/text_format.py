import ast

import parse
from glom import glom
from html2text import html2text

input_spec_parse_pattern = "{" * 5 + "}" * 5


def daras_ai_format_str(format_str, variables, do_html2text=False):
    input_spec_results: list[parse.Result] = list(
        parse.findall(input_spec_parse_pattern, format_str)
    )
    for spec_result in input_spec_results:
        spec = spec_result.fixed[0]
        variable_value = glom(variables, ast.literal_eval(spec))
        if variable_value is None:
            variable_value = ""
        else:
            variable_value = str(variable_value)
        if do_html2text:
            variable_value = html2text(variable_value)
        if isinstance(variable_value, str):
            variable_value = variable_value.strip()
        format_str = format_str.replace("{{" + spec + "}}", str(variable_value))
    return format_str

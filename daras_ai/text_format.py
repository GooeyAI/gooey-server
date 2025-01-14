import ast
import re
import parse
from markdown_it import MarkdownIt

from daras_ai_v2.tts_markdown_renderer import RendererPlain


input_spec_parse_pattern = "{" * 5 + "}" * 5


def daras_ai_format_str(format_str, variables):
    from glom import glom

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
        if isinstance(variable_value, str):
            variable_value = variable_value.strip()
        format_str = format_str.replace("{{" + spec + "}}", str(variable_value))
    return format_str


def format_number_with_suffix(num: int) -> str:
    """
    Formats large number with a suffix.

    Ref: https://stackoverflow.com/a/45846841
    """
    num_float = float("{:.3g}".format(num))
    magnitude = 0
    while abs(num_float) >= 1000:
        magnitude += 1
        num_float /= 1000.0
    return "{}{}".format(
        "{:f}".format(num_float).rstrip("0").rstrip("."),
        ["", "K", "M", "B", "T"][magnitude],
    )


def unmarkdown(text: str) -> str:
    """markdown to plaintext"""
    return MarkdownIt(renderer_cls=RendererPlain).render(text)


def wa_markdown(text: str) -> str:
    patterns = [
        (
            re.compile(r"^(#+)\s+(.*)$", flags=re.MULTILINE),
            lambda m: f"*{m.group(2)}*",
        ),  # "# headings" -> "*headings*"
        (
            re.compile(r"\*\*(.+?)\*\*"),
            lambda m: f"*{m.group(1)}*",
        ),  # "**bold**"" -> "*bold*"
        (
            re.compile(r"~~(.+?)~~"),
            lambda m: f"~{m.group(1)}~",
        ),  # "~~text~~" -> "~text~"
    ]

    for pattern, repl in patterns:
        text = pattern.sub(repl, text)

    return text

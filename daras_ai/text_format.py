import ast
import re
import parse
from typing import Mapping, Any

from markdown_it import MarkdownIt
from mdformat.renderer import MDRenderer

from daras_ai.mdit_wa_plugin import WhatsappParser
from daras_ai_v2.tts_markdown_renderer import RendererPlain
from daras_ai_v2.text_splitter import new_para


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


WA_FORMATTING_OPTIONS: Mapping[str, Any] = {
    "mdformat": {"number": True},
    "parser_extension": [WhatsappParser],
}


def wa_markdown(text: str) -> str:
    """commonmark to WA compatible Markdown"""

    if text is None:
        return ""

    md = MarkdownIt("commonmark").enable("table").enable("strikethrough")

    tokens = md.parse(text)
    return MDRenderer().render(tokens, options=WA_FORMATTING_OPTIONS, env={})


def is_list_item_complete(text: str) -> bool:
    """Returns True if the last block is a list item, False otherwise."""

    if text is None:
        return False
    blocks = re.split(new_para, text.strip())

    if not blocks:
        return False

    last_block = blocks[-1].strip()
    lines = [ln for ln in last_block.split("\n") if ln.strip()]
    list_item_pattern = re.compile(r"^\s*(?:[*+\-]|\d+\.)\s+")

    is_list_block = any(list_item_pattern.match(ln) for ln in lines)

    return is_list_block

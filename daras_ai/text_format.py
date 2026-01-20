import ast
import datetime

import markdown_it
import markdown_it.presets
import parse

from daras_ai_v2.tts_markdown_renderer import RendererPlain
from daras_ai_v2.wa_markdown_renderer import RendererWhatsApp

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


def format_timedelta(td: datetime.timedelta) -> str:
    seconds = max(round(td.total_seconds()), 1)  # avoid 0s, dont show ms
    return str(datetime.timedelta(seconds=seconds))


def format_number_with_suffix(num: int) -> str:
    """
    Formats large number with a suffix.

        return f"{td.seconds}s"
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
    return markdown_it.MarkdownIt(renderer_cls=RendererPlain).render(text)


def markdown_to_wa(text: str) -> tuple[str, list[str]]:
    """markdown to whatsapp"""
    md = markdown_it.MarkdownIt(renderer_cls=RendererWhatsApp)

    def _render_line(line: str) -> str:
        if not line:
            return "\n"
        content = line.lstrip()
        whitespace = line[: -len(content)]
        ret = md.render(content)
        if not ret:
            return whitespace
        return whitespace + ret + "\n"

    return (
        "".join(map(_render_line, text.split("\n"))),
        md.renderer.collected_media_urls,
    )

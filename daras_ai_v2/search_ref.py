import re
import typing

import jinja2


class SearchReference(typing.TypedDict):
    url: str
    title: str
    snippet: str
    score: float


pat = re.compile(
    r"(" + r"(\[" + "[\d,\s\.\,\]\[]+" + "\])+" + r")+",
)


def render_text_with_refs(text: str, references: list[SearchReference]):
    html = ""
    for snippet, refs in parse_refs(text, references):
        html += snippet
        if not refs:
            continue
        ref_html = ", ".join(
            [f'<a href="{ref["url"]}">{ref_num}</a>' for ref_num, ref in refs.items()]
        )
        html += f"<sup>[{ref_html}]</sup>"
    return html


def apply_response_template(output_text: list[str], references: list[SearchReference]):
    for i, text in enumerate(output_text):
        formatted = ""
        all_refs = {}
        for snippet, ref_map in parse_refs(text, references):
            formatted += (
                snippet
                + " "
                + " ".join(f"[{ref_num}]" for ref_num in ref_map.keys())
                + " "
            )
            all_refs.update(ref_map)
        for ref_num, ref in all_refs.items():
            try:
                template = ref["response_template"]
            except KeyError:
                pass
            else:
                formatted = jinja2.Template(template).render(
                    **ref,
                    output_text=formatted,
                    ref_num=ref_num,
                )
        output_text[i] = formatted


def parse_refs(
    text: str, references: list[SearchReference]
) -> typing.Generator[typing.Tuple[str, dict[int, SearchReference]], None, None]:
    """
    Parse references embedded inside text.

    Args:
        text: Text to parse.
        references: List of references to use.

    Returns:
        Generator of tuples of (snippet, references).
        references is a dict of the reference number to reference. reference number is 1-indexed.
    """
    last_match_end = 0
    for match in pat.finditer(text):
        ref_str = text[match.start() : match.end()].strip()
        ref_numbers = set(int(num) for num in re.findall(r"\d+", ref_str))
        refs = {}
        for ref_num in ref_numbers:
            try:
                refs[ref_num] = references[ref_num - 1]
            except IndexError:
                continue
        yield text[last_match_end : match.start()].strip(), refs
        last_match_end = match.end()
    end_text = text[last_match_end:]
    if end_text:
        yield end_text, {}

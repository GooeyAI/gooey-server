import re
import typing
from enum import Enum

import jinja2

import gooey_ui
from daras_ai_v2.scrollable_html_widget import scrollable_html


class SearchReference(typing.TypedDict):
    url: str
    title: str
    snippet: str
    score: float


class CitationStyles(Enum):
    number = "Numerical ( [1] [2] [3] ..)"
    title = "Source Title ( [Source 1] [Source 2] [Source 3] ..)"
    url = "Source URL ( [https://source1.com] [https://source2.com] [https://source3.com] ..)"
    markdown = "Markdown ( [Source 1](https://source1.com) [Source 2](https://source2.com) [Source 3](https://source3.com) ..)"
    html = "HTML ( <a href='https://source1.com'>Source 1</a> <a href='https://source2.com'>Source 2</a> <a href='https://source3.com'>Source 3</a> ..)"
    slack_mrkdwn = "Slack mrkdwn ( <https://source1.com|Source 1> <https://source2.com|Source 2> <https://source3.com|Source 3> ..)"


def remove_quotes(snippet: str) -> str:
    return re.sub(r"[\"\']+", r'"', snippet).strip()


def render_text_with_refs(text: str, references: list[SearchReference]):
    html = ""
    for snippet, refs in parse_refs(text, references):
        html += snippet
        if not refs:
            continue
        ref_html = ", ".join(
            [
                f'<a target="_blank" href="{ref["url"]}">{ref_num}</a>'
                for ref_num, ref in refs.items()
            ]
        )
        html += f"<sup>[{ref_html}]</sup>"
    # convert newlines to <br> and paragraphs
    html = re.sub(r"\n\s*\n", r"</p><p>", "<p>" + html + "</p>").replace("\n", "<br>")
    return html


def apply_response_template(
    output_text: list[str],
    references: list[SearchReference],
    citation_style: CitationStyles | None = CitationStyles.number,
):
    for i, text in enumerate(output_text):
        formatted = ""
        all_refs = {}
        for snippet, ref_map in parse_refs(text, references):
            match citation_style:
                case CitationStyles.number:
                    cites = " ".join(f"[{ref_num}]" for ref_num in ref_map.keys())
                case CitationStyles.title:
                    cites = " ".join(f"[{ref['title']}]" for ref in ref_map.values())
                case CitationStyles.url:
                    cites = " ".join(f"[{ref['url']}]" for ref in ref_map.values())
                case CitationStyles.markdown:
                    cites = " ".join(
                        f"[{ref['title']}]({ref['url']})" for ref in ref_map.values()
                    )
                case CitationStyles.html:
                    cites = " ".join(
                        f"<a href='{ref['url']}'>{ref['title']}</a>"
                        for ref in ref_map.values()
                    )
                case CitationStyles.slack_mrkdwn:
                    cites = " ".join(
                        f"<{ref['url']}|{ref['title']}>" for ref in ref_map.values()
                    )
                case None:
                    cites = ""
                case _:
                    raise ValueError(f"Unknown citation style: {citation_style}")
            formatted += snippet + " " + cites + " "
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


search_ref_pat = re.compile(r"\[" r"[\d\s\.\,\[\]\$\{\}]+" r"\]")


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
    for match in search_ref_pat.finditer(text):
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


def render_output_with_refs(state, height):
    output_text = state.get("output_text", [])
    if output_text:
        gooey_ui.write("**Answer**")
    for text in output_text:
        html = render_text_with_refs(text, state.get("references", []))
        scrollable_html(html, height=height)

import re
import typing
from enum import Enum

import jinja2
from typing_extensions import TypedDict

import gooey_ui
from daras_ai_v2.exceptions import UserError
from daras_ai_v2.scrollable_html_widget import scrollable_html


class SearchReference(TypedDict):
    url: str
    title: str
    snippet: str
    score: float


class CitationStyles(Enum):
    number = "Numbers ( [1] [2] [3] ..)"
    title = "Source Title ( [Source 1] [Source 2] [Source 3] ..)"
    url = "Source URL ( [https://source1.com] [https://source2.com] [https://source3.com] ..)"
    symbol = "Symbols ( [*] [†] [‡] ..)"

    markdown = "Markdown ( [Source 1](https://source1.com) [Source 2](https://source2.com) [Source 3](https://source3.com) ..)"
    html = "HTML ( <a href='https://source1.com'>Source 1</a> <a href='https://source2.com'>Source 2</a> <a href='https://source3.com'>Source 3</a> ..)"
    slack_mrkdwn = "Slack mrkdwn ( <https://source1.com|Source 1> <https://source2.com|Source 2> <https://source3.com|Source 3> ..)"
    plaintext = "Plain Text / WhatsApp ( [Source 1 https://source1.com] [Source 2 https://source2.com] [Source 3 https://source3.com] ..)"

    number_markdown = "Markdown Numbers + Footnotes"
    number_html = "HTML Numbers + Footnotes"
    number_slack_mrkdwn = "Slack mrkdown Numbers + Footnotes"
    number_plaintext = "Plain Text / WhatsApp Numbers + Footnotes"

    symbol_markdown = "Markdown Symbols + Footnotes"
    symbol_html = "HTML Symbols + Footnotes"
    symbol_slack_mrkdwn = "Slack mrkdown Symbols + Footnotes"
    symbol_plaintext = "Plain Text / WhatsApp Symbols + Footnotes"


def remove_quotes(snippet: str) -> str:
    return re.sub(r"[\"\']+", r'"', snippet).strip()


def render_text_with_refs(text: str, references: list[SearchReference]):
    html = ""
    for snippet, refs in parse_refs(text, references):
        html += snippet
        if not refs:
            continue
        ref_html = ", ".join(
            html_link(str(ref_num), ref["url"]) for ref_num, ref in refs.items()
        )
        html += f"<sup>[{ref_html}]</sup>"
    # convert newlines to <br> and paragraphs
    html = re.sub(r"\n\s*\n", r"</p><p>", "<p>" + html + "</p>").replace("\n", "<br>")
    return html


def apply_response_formattings_prefix(
    output_text: list[str],
    references: list[SearchReference],
    citation_style: CitationStyles | None = CitationStyles.number,
) -> list[dict[int, SearchReference]]:
    all_refs_list = [{}] * len(output_text)
    for i, text in enumerate(output_text):
        all_refs_list[i], output_text[i] = format_citations(
            text, references, citation_style
        )
    return all_refs_list


def apply_response_formattings_suffix(
    all_refs_list: list[dict[int, SearchReference]],
    output_text: list[str],
    citation_style: CitationStyles | None = CitationStyles.number,
):
    for i, text in enumerate(output_text):
        output_text[i] = format_jinja_response_template(
            all_refs_list[i],
            format_footnotes(all_refs_list[i], text, citation_style),
        )


def format_citations(
    text: str,
    references: list[SearchReference],
    citation_style: CitationStyles | None = CitationStyles.number,
) -> tuple[dict[int, SearchReference], str]:
    all_refs = {}
    formatted = ""
    for snippet, ref_map in parse_refs(text, references):
        match citation_style:
            case CitationStyles.number | CitationStyles.number_plaintext:
                cites = " ".join(f"[{ref_num}]" for ref_num in ref_map.keys())
            case CitationStyles.title:
                cites = " ".join(f"[{ref['title']}]" for ref in ref_map.values())
            case CitationStyles.url:
                cites = " ".join(f"[{ref['url']}]" for ref in ref_map.values())
            case CitationStyles.symbol | CitationStyles.symbol_plaintext:
                cites = " ".join(
                    f"[{generate_footnote_symbol(ref_num - 1)}]"
                    for ref_num in ref_map.keys()
                )

            case CitationStyles.markdown:
                cites = " ".join(ref_to_markdown(ref) for ref in ref_map.values())
            case CitationStyles.html:
                cites = " ".join(ref_to_html(ref) for ref in ref_map.values())
            case CitationStyles.slack_mrkdwn:
                cites = " ".join(ref_to_slack_mrkdwn(ref) for ref in ref_map.values())
            case CitationStyles.plaintext:
                cites = " ".join(
                    f'[{ref["title"]} {ref["url"]}]' for ref_num, ref in ref_map.items()
                )

            case CitationStyles.number_markdown:
                cites = " ".join(
                    markdown_link(f"[{ref_num}]", ref["url"])
                    for ref_num, ref in ref_map.items()
                )
            case CitationStyles.number_html:
                cites = " ".join(
                    html_link(f"[{ref_num}]", ref["url"])
                    for ref_num, ref in ref_map.items()
                )
            case CitationStyles.number_slack_mrkdwn:
                cites = " ".join(
                    slack_mrkdwn_link(f"[{ref_num}]", ref["url"])
                    for ref_num, ref in ref_map.items()
                )

            case CitationStyles.symbol_markdown:
                cites = " ".join(
                    markdown_link(
                        f"[{generate_footnote_symbol(ref_num - 1)}]", ref["url"]
                    )
                    for ref_num, ref in ref_map.items()
                )
            case CitationStyles.symbol_html:
                cites = " ".join(
                    html_link(f"[{generate_footnote_symbol(ref_num - 1)}]", ref["url"])
                    for ref_num, ref in ref_map.items()
                )
            case CitationStyles.symbol_slack_mrkdwn:
                cites = " ".join(
                    slack_mrkdwn_link(
                        f"[{generate_footnote_symbol(ref_num - 1)}]", ref["url"]
                    )
                    for ref_num, ref in ref_map.items()
                )
            case None:
                cites = ""
            case _:
                raise UserError(f"Unknown citation style: {citation_style}")
        formatted += " ".join(filter(None, [snippet, cites]))
        all_refs.update(ref_map)
    return all_refs, formatted


def format_footnotes(
    all_refs: dict[int, SearchReference], formatted: str, citation_style: CitationStyles
) -> str:
    if not all_refs:
        return formatted
    match citation_style:
        case CitationStyles.number_markdown:
            formatted += "\n\n"
            formatted += "  \n".join(
                f"[{ref_num}] {ref_to_markdown(ref)}"
                for ref_num, ref in sorted(all_refs.items())
            )
        case CitationStyles.number_html:
            formatted += "<br><br>"
            formatted += "<br>".join(
                f"[{ref_num}] {ref_to_html(ref)}"
                for ref_num, ref in sorted(all_refs.items())
            )
        case CitationStyles.number_slack_mrkdwn:
            formatted += "\n\n"
            formatted += "\n".join(
                f"[{ref_num}] {ref_to_slack_mrkdwn(ref)}"
                for ref_num, ref in sorted(all_refs.items())
            )
        case CitationStyles.number_plaintext:
            formatted += "\n\n"
            formatted += "\n".join(
                f'{ref_num}. {ref["title"]} {ref["url"]}'
                for ref_num, ref in sorted(all_refs.items())
            )

        case CitationStyles.symbol_markdown:
            formatted += "\n\n"
            formatted += "  \n".join(
                f"{generate_footnote_symbol(ref_num - 1)} {ref_to_markdown(ref)}"
                for ref_num, ref in sorted(all_refs.items())
            )
        case CitationStyles.symbol_html:
            formatted += "<br><br>"
            formatted += "<br>".join(
                f"{generate_footnote_symbol(ref_num - 1)} {ref_to_html(ref)}"
                for ref_num, ref in sorted(all_refs.items())
            )
        case CitationStyles.symbol_slack_mrkdwn:
            formatted += "\n\n"
            formatted += "\n".join(
                f"{generate_footnote_symbol(ref_num - 1)} {ref_to_slack_mrkdwn(ref)}"
                for ref_num, ref in sorted(all_refs.items())
            )
        case CitationStyles.symbol_plaintext:
            formatted += "\n\n"
            formatted += "\n".join(
                f'{generate_footnote_symbol(ref_num - 1)}. {ref["title"]} {ref["url"]}'
                for ref_num, ref in sorted(all_refs.items())
            )
    return formatted


def format_jinja_response_template(
    all_refs: dict[int, SearchReference], formatted: str
) -> str:
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
    return formatted


search_ref_pat = re.compile(r"\[" r"[\d\s\.\,\[\]\$\{\}]+" r"\]")


def ref_to_markdown(ref: SearchReference) -> str:
    return markdown_link(ref["title"], ref["url"])


def ref_to_html(ref: SearchReference) -> str:
    return html_link(ref["title"], ref["url"])


def ref_to_slack_mrkdwn(ref: SearchReference) -> str:
    return slack_mrkdwn_link(ref["title"], ref["url"])


def markdown_link(title: str, url: str) -> str:
    return f"[{title}]({url})"


def html_link(title: str, url: str) -> str:
    return f'<a target="_blank" href="{url}">{title}</a>'


def slack_mrkdwn_link(title: str, url: str) -> str:
    return f"<{url}|{title}>"


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


def render_output_with_refs(state, height=500):
    output_text = state.get("output_text", [])
    for text in output_text:
        html = render_text_with_refs(text, state.get("references", []))
        scrollable_html(html, height=height)


FOOTNOTE_SYMBOLS = ["*", "†", "‡", "§", "¶", "#", "♠", "♥", "♦", "♣", "✠", "☮", "☯", "✡"]  # fmt: skip
def generate_footnote_symbol(idx: int) -> str:
    quotient, remainder = divmod(idx, len(FOOTNOTE_SYMBOLS))
    return FOOTNOTE_SYMBOLS[remainder] * (quotient + 1)

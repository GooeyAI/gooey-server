import ast
import re
import parse
import requests
from typing import Mapping, Any

from furl import furl
from markdown_it import MarkdownIt
from mdformat.renderer import MDRenderer

from daras_ai.image_input import upload_file_from_bytes
from daras_ai.mdit_wa_plugin import WhatsappParser
from daras_ai_v2.exceptions import raise_for_status
from daras_ai_v2.tts_markdown_renderer import RendererPlain
from daras_ai_v2.text_splitter import new_para
from loguru import logger


input_spec_parse_pattern = "{" * 5 + "}" * 5

WA_FORMATTING_OPTIONS: Mapping[str, Any] = {
    "mdformat": {"number": True},
    "parser_extension": [WhatsappParser],
}

WHATSAPP_VALID_IMAGE_FORMATS = [
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/tiff",
    "image/webp",
    "image/bmp",
]


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


def extract_image_urls(tokens) -> list[str]:
    image_urls = []

    for token in tokens:
        if token.type == "inline" and token.children:
            for child in token.children:
                if child.type == "image" and "src" in child.attrs:
                    image_urls.append(child.attrs["src"])

    return image_urls


def get_mimetype_from_url(url: str) -> str:
    try:
        r = requests.head(url)
        raise_for_status(r)
        return r.headers.get("content-type", "application/octet-stream")
    except requests.RequestException as e:
        logger.warning(f"Error fetching mimetype for {url}: {e}")
        return "application/octet-stream"


def process_wa_image_urls(image_urls: list[str]) -> list[str]:
    from wand.image import Image

    processed_images = []
    for image_url in image_urls:

        parsed_url = furl(image_url)
        if parsed_url.scheme not in ["http", "https"]:
            continue

        mime_type = get_mimetype_from_url(image_url)

        if mime_type in WHATSAPP_VALID_IMAGE_FORMATS:
            r = requests.get(image_url)
            raise_for_status(r)
            filename = (
                r.headers.get("content-disposition", "")
                .split("filename=")[-1]
                .strip('"')
            )
            image_data = r.content

            with Image(blob=image_data) as img:
                if img.format.lower() not in ["png", "jpeg"]:
                    png_blob = img.make_blob(format="png")
                    processed_images.append(
                        upload_file_from_bytes(filename, png_blob, "image/png")
                    )
                else:
                    processed_images.append(image_url)

    return processed_images


def wa_markdown(text: str) -> str | tuple[list[str | Any], str]:
    """commonmark to WA compatible Markdown"""

    if text is None:
        return ""

    md = MarkdownIt("commonmark").enable("strikethrough")
    tokens = md.parse(text)
    image_urls = extract_image_urls(tokens)
    processed_images = process_wa_image_urls(image_urls)
    whatsapp_msg_text = MDRenderer().render(
        tokens, options=WA_FORMATTING_OPTIONS, env={}
    )
    return processed_images, whatsapp_msg_text


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

import json
import tempfile
import typing
from enum import Enum

from daras_ai.image_input import upload_file_from_bytes
from daras_ai_v2.settings import templates


def json_to_pdf(filename: str, data: str) -> str:
    html = templates.get_template("form_output.html").render(data=json.loads(data))
    pdf_bytes = html_to_pdf(html)
    if not filename.endswith(".pdf"):
        filename += ".pdf"
    return upload_file_from_bytes(filename, pdf_bytes, "application/pdf")


def html_to_pdf(html: str) -> bytes:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(html)
        with tempfile.NamedTemporaryFile(suffix=".pdf") as outfile:
            page.pdf(path=outfile.name, format="A4")
            ret = outfile.read()
        browser.close()

    return ret


class LLMTools(Enum):
    json_to_pdf = (
        json_to_pdf,
        "Save JSON as PDF",
        {
            "type": "function",
            "function": {
                "name": json_to_pdf.__name__,
                "description": "Save JSON data to PDF",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filename": {
                            "type": "string",
                            "description": "A short but descriptive filename for the PDF",
                        },
                        "data": {
                            "type": "string",
                            "description": "The JSON data to write to the PDF",
                        },
                    },
                    "required": ["filename", "data"],
                },
            },
        },
    )
    # send_reply_buttons = (print, "Send back reply buttons to the user.", {})

    def __new__(cls, fn: typing.Callable, label: str, spec: dict):
        obj = object.__new__(cls)
        obj._value_ = fn.__name__
        obj.fn = fn
        obj.label = label
        obj.spec = spec
        return obj

    # def __init__(self, *args, **kwargs):
    #     self._value_ = self.name

import requests
from aifail import retry_if

from daras_ai_v2 import settings
from daras_ai_v2.exceptions import UserError, raise_for_status

MISTRAL_OCR_URL = "https://api.mistral.ai/v1/ocr"
MISTRAL_OCR_TABLE_FORMAT = "markdown"


def mistral_should_retry(e: Exception) -> bool:
    if isinstance(
        e, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)
    ):
        return True
    if not isinstance(e, requests.exceptions.HTTPError) or e.response is None:
        return False
    status_code = e.response.status_code
    return status_code in (408, 429, 502, 503, 504) or (
        status_code == 500 and "service unavailable" in (e.response.text.lower() or "")
    )


@retry_if(mistral_should_retry, max_retries=3)
def run_mistral_ocr_on_page(
    url: str, page_num: int, model_id: str = "mistral-ocr-latest"
) -> str:
    if not settings.MISTRAL_API_KEY:
        raise UserError("Mistral OCR is not configured: missing MISTRAL_API_KEY")

    payload = {
        "model": model_id,
        "document": {"type": "document_url", "document_url": url},
        # Mistral OCR expects zero-based page indexes.
        "pages": [page_num - 1],
        "table_format": MISTRAL_OCR_TABLE_FORMAT,
        "include_image_base64": False,
    }
    headers = {
        "Authorization": f"Bearer {settings.MISTRAL_API_KEY}",
        "Content-Type": "application/json",
    }
    r = requests.post(
        MISTRAL_OCR_URL,
        headers=headers,
        json=payload,
        timeout=60,
    )
    raise_for_status(r)

    data = r.json()
    pages = data.get("pages")
    if not pages:
        return ""
    return _page_to_text(pages[0])


def _page_to_text(page: dict) -> str:
    markdown = (page.get("markdown") or "").strip()
    tables = page.get("tables") or []
    for table in tables:
        table_id = table.get("id")
        table_content = table.get("content")
        if not (table_id and table_content):
            continue
        placeholder = f"[{table_id}]({table_id})"
        if placeholder in markdown:
            markdown = markdown.replace(placeholder, table_content)
        else:
            markdown += f"\n\n{table_content}"
    return markdown

import csv
import io
import re
import typing
from time import sleep

import requests
from furl import furl
from jinja2.lexer import whitespace_re

from daras_ai_v2 import settings
from daras_ai_v2.exceptions import raise_for_status
from daras_ai_v2.redis_cache import redis_cache_decorator
from daras_ai_v2.text_splitter import default_length_function

auth_headers = {"Ocp-Apim-Subscription-Key": settings.AZURE_FORM_RECOGNIZER_KEY}


def azure_doc_extract_page_num(pdf_url: str, page_num: int) -> str:
    if page_num:
        params = dict(pages=str(page_num))
    else:
        params = None
    pages = azure_doc_extract_pages(pdf_url, params=params)
    if pages and pages[0]:
        return str(pages[0])
    else:
        return ""


def azure_doc_extract_pages(
    pdf_url: str, model_id: str = "prebuilt-layout", params: dict = None
) -> list[str]:
    result = azure_form_recognizer(pdf_url, model_id, params)
    return [
        records_to_text(extract_records(result, page["pageNumber"]))
        for page in result["pages"]
    ]


@redis_cache_decorator(ex=settings.REDIS_MODELS_CACHE_EXPIRY)
def azure_form_recognizer_models() -> dict[str, str]:
    r = requests.get(
        str(
            furl(settings.AZURE_FORM_RECOGNIZER_ENDPOINT)
            / "formrecognizer/documentModels"
        ),
        params={"api-version": "2023-07-31"},
        headers=auth_headers,
    )
    raise_for_status(r)
    return {value["modelId"]: value["description"] for value in r.json()["value"]}


@redis_cache_decorator(ex=settings.REDIS_MODELS_CACHE_EXPIRY)
def azure_form_recognizer(url: str, model_id: str, params: dict = None):
    r = requests.post(
        str(
            furl(settings.AZURE_FORM_RECOGNIZER_ENDPOINT)
            / f"formrecognizer/documentModels/{model_id}:analyze"
        ),
        params={"api-version": "2023-07-31"} | (params or {}),
        headers=auth_headers,
        json={"urlSource": url},
    )
    raise_for_status(r)
    location = r.headers["Operation-Location"]
    while True:
        r = requests.get(location, headers=auth_headers)
        raise_for_status(r)
        r_json = r.json()
        match r_json.get("status"):
            case "succeeded":
                return r_json["analyzeResult"]
            case "failed":
                raise Exception(r_json)
            case _:
                sleep(1)


def extract_records(result: dict, page_num: int) -> list[dict]:
    table_polys = extract_tables(result, page_num)
    records = []
    for para in result.get("paragraphs", []):
        try:
            if para["boundingRegions"][0]["pageNumber"] != page_num:
                continue
        except (KeyError, IndexError):
            continue
        for table in table_polys:
            if rect_contains(
                outer=table["polygon"], inner=para["boundingRegions"][0]["polygon"]
            ):
                if not table.get("added"):
                    records.append({"role": "csv", "content": table["content"]})
                    table["added"] = True
                break
        else:
            records.append(
                {
                    "role": para.get("role", ""),
                    "content": strip_content(para["content"]),
                }
            )
    return records


def records_to_text(records: list[dict]) -> str:
    ret = ""
    last_role = None
    for record in records:
        content = record["content"].strip()
        role = record["role"] or "content"
        if role != last_role:
            last_role = role
            ret += f"{last_role}={content}\n"
        else:
            ret += f"{content}\n"
    return ret.strip()


def rect_contains(*, outer: list[int], inner: list[int]):
    tl_x, tl_y, tr_x, tr_y, br_x, br_y, bl_x, bl_y = outer
    for pt_x, pt_y in zip(inner[::2], inner[1::2]):
        # if the point is inside the bounding box, return True
        if tl_x <= pt_x <= tr_x and tl_y <= pt_y <= bl_y:
            return True
    return False


def extract_tables(result, page):
    table_polys = []
    for table in result["tables"]:
        try:
            if table["boundingRegions"][0]["pageNumber"] != page:
                continue
        except (KeyError, IndexError):
            continue
        plain = table_to_csv(table)
        table_polys.append(
            {
                "polygon": table["boundingRegions"][0]["polygon"],
                "content": plain,
                "added": False,
            }
        )
    return table_polys


def table_to_csv(table: dict) -> str:
    return table_arr_to_csv(table_to_arr(table))


THEAD = "**"


def table_to_arr(table: dict) -> list[list[str]]:
    with open(f"table-{table['columnCount']}.json", "w") as f:
        f.write(str(table))
    arr = [["" for _ in range(table["columnCount"])] for _ in range(table["rowCount"])]
    for cell in table["cells"]:
        for i in range(cell.get("rowSpan", 1)):
            row_idx = cell["rowIndex"] + i
            for j in range(cell.get("columnSpan", 1)):
                col_idx = cell["columnIndex"] + j
                content = strip_content(cell["content"])
                if cell.get("kind") in ("rowHeader", "columnHeader", "stubHead"):
                    content = THEAD + content + THEAD
                arr[row_idx][col_idx] = content
    return arr


# NOTE:  These are individual tokens in the gpt-4 vocab, and must be handled with care
THEAD_SEP = "|--"
TROW_END = "|\n"
TROW_SEP = " |"


def table_arr_to_prompt(arr: typing.Iterable[list[str]]) -> str:
    text = ""
    prev_is_header = True
    for row in arr:
        is_header = _strip_header_from_row(row)
        row = _remove_long_dupe_header(row)
        if prev_is_header and not is_header:
            text += THEAD_SEP * len(row) + TROW_END
        text += TROW_SEP + TROW_SEP.join(row) + TROW_END
        prev_is_header = is_header
    return text


def table_arr_to_prompt_chunked(
    arr: typing.Iterable[list[str]], chunk_size: int
) -> typing.Iterable[str]:
    header = ""
    chunk = ""
    prev_is_header = True
    for row in arr:
        is_header = _strip_header_from_row(row)
        row = _remove_long_dupe_header(row)
        if prev_is_header and not is_header:
            header += THEAD_SEP * len(row) + TROW_END
        next_chunk = TROW_SEP + TROW_SEP.join(row) + TROW_END
        if is_header:
            header += next_chunk
            if default_length_function(header) > chunk_size:
                yield header
                header = ""
        else:
            if default_length_function(header + chunk + next_chunk) > chunk_size:
                yield header + chunk.rstrip()
                chunk = ""
            chunk += next_chunk
        prev_is_header = is_header
    if chunk:
        yield header + chunk.rstrip()


def _strip_header_from_row(row):
    is_header = False
    for i, cell in enumerate(row):
        if cell.startswith(THEAD) and cell.endswith(THEAD):
            row[i] = cell[len(THEAD) : -len(THEAD)]
            is_header = True
    return is_header


def _remove_long_dupe_header(row: list[str], cutoff: int = 2) -> list[str]:
    r = -1
    l = 0
    for cell in row[-2::-1]:
        if not row[r]:
            r -= 1
            l -= 1
            continue
        if cell == row[r]:
            l -= 1
        else:
            break
    if -l >= cutoff:
        row = row[:l] + [""] * -l
    return row


def table_arr_to_csv(arr: typing.Iterable[list[str]]) -> str:
    f = io.StringIO()
    writer = csv.writer(f)
    writer.writerows(arr)
    return f.getvalue()


selection_marks_re = re.compile(r":(un)?selected:")


def strip_content(text: str) -> str:
    text = selection_marks_re.sub("", text)
    text = whitespace_re.sub(" ", text)
    return text.strip()

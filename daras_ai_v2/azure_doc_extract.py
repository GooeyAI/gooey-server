import requests
from furl import furl
from tabulate import tabulate

from daras_ai_v2 import settings
from daras_ai_v2.redis_cache import redis_cache_decorator
from gooeysite import wsgi

assert wsgi

from time import sleep

auth_headers = {"Ocp-Apim-Subscription-Key": settings.AZURE_FORM_RECOGNIZER_KEY}


def azure_pdf_extract(pdf_url: str):
    r = requests.post(
        str(
            furl(settings.AZURE_FORM_RECOGNIZER_ENDPOINT)
            / "formrecognizer/documentModels/prebuilt-document:analyze"
        ),
        params={"api-version": "2023-07-31"},
        headers=auth_headers,
        json={"urlSource": pdf_url},
    )
    r.raise_for_status()
    location = r.headers["Operation-Location"]
    while True:
        r = requests.get(
            location,
            headers=auth_headers,
        )
        r.raise_for_status()
        r_json = r.json()
        match r_json.get("status"):
            case "succeeded":
                result = r_json["analyzeResult"]
                return [
                    records_to_text(extract_records(result, page["pageNumber"]))
                    for page in result["pages"]
                ]
            case "failed":
                raise Exception(r_json)
            case _:
                sleep(1)


@redis_cache_decorator
def extract_records(result: dict, page_num: int) -> list[dict]:
    table_polys = extract_tables(result, page_num)
    records = []
    for para in result["paragraphs"]:
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
                    records.append({"role": "table", "content": table["content"]})
                    table["added"] = True
                break
        else:
            records.append({"role": para.get("role", ""), "content": para["content"]})
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


# def table_to_html(table):
#     with redirect_stdout(io.StringIO()) as f:
#         print("<table>")
#         print("<tr>")
#         idx = 0
#         for cell in table["cells"]:
#             if idx != cell["rowIndex"]:
#                 print("</tr>")
#                 print("<tr>")
#             idx = cell["rowIndex"]
#             if cell.get("kind") == "columnHeader":
#                 tag = "th"
#             else:
#                 tag = "td"
#             print(
#                 f"<{tag} rowspan={cell.get('rowSpan', 1)} colspan={cell.get('columnSpan',1)}>{cell['content'].strip()}</{tag}>"
#             )
#         print("</tr>")
#         print("</table>")
#         return f.getvalue()


def extract_tables(result, page):
    table_polys = []
    for table in result["tables"]:
        try:
            if table["boundingRegions"][0]["pageNumber"] != page:
                continue
        except (KeyError, IndexError):
            continue
        plain = table_to_plain(table)
        table_polys.append(
            {
                "polygon": table["boundingRegions"][0]["polygon"],
                "content": plain,
                "added": False,
            }
        )
    return table_polys


def rect_contains(*, outer: list[int], inner: list[int]):
    tl_x, tl_y, tr_x, tr_y, br_x, br_y, bl_x, bl_y = outer
    for pt_x, pt_y in zip(inner[::2], inner[1::2]):
        # if the point is inside the bounding box, return True
        if tl_x <= pt_x <= tr_x and tl_y <= pt_y <= bl_y:
            return True
    return False


def table_to_plain(table):
    ret = [["" for _ in range(table["columnCount"])] for _ in range(table["rowCount"])]
    for cell in table["cells"]:
        ret[cell["rowIndex"]][cell["columnIndex"]] = cell["content"].strip()
    return tabulate(ret, tablefmt="plain")

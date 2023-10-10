import io
import typing

import pandas as pd
import requests
from fastapi import HTTPException
from furl import furl
from pydantic import BaseModel

import gooey_ui as st
from bots.models import Workflow
from daras_ai.image_input import upload_file_from_bytes
from daras_ai_v2.base import BasePage
from daras_ai_v2.doc_search_settings_widgets import document_uploader
from daras_ai_v2.functional import map_parallel
from daras_ai_v2.query_params_util import extract_query_params
from recipes.DocSearch import render_documents

CACHED_COLUMNS = "__cached_columns"


class BulkRunnerPage(BasePage):
    title = "Bulk Runner"
    workflow = Workflow.BULK_RUNNER
    slug_versions = ["bulk-runner", "bulk"]

    class RequestModel(BaseModel):
        documents: list[str]
        run_urls: list[str]

        input_columns: dict[str, str]
        output_columns: dict[str, str]

    class ResponseModel(BaseModel):
        output_documents: list[str]

    def fields_to_save(self) -> [str]:
        return super().fields_to_save() + [CACHED_COLUMNS]

    def render_form_v2(self):
        from daras_ai_v2.all_pages import page_slug_map, normalize_slug

        run_urls = st.session_state.get("run_urls", "")
        st.session_state.setdefault("__run_urls", "\n".join(run_urls))
        run_urls = (
            st.text_area("##### Run URL(s)", key="__run_urls").strip().splitlines()
        )
        st.session_state["run_urls"] = run_urls

        files = document_uploader(
            "##### Upload a File",
            accept=(".csv", ".xlsx", ".xls", ".json", ".tsv", ".xml"),
        )

        if files:
            st.session_state[CACHED_COLUMNS] = list(
                {
                    col: None
                    for df in map_parallel(_read_df, files)
                    for col in df.columns
                    if not col.startswith("Unnamed:")
                }
            )
        else:
            st.session_state.pop(CACHED_COLUMNS, None)

        required_input_fields = {}
        optional_input_fields = {}
        output_fields = {}

        for url in run_urls:
            f = furl(url)
            slug = f.path.segments[0]
            try:
                page_cls = page_slug_map[normalize_slug(slug)]
            except KeyError as e:
                st.error(repr(e))
                continue

            example_id, run_id, uid = extract_query_params(f.query.params)
            try:
                sr = page_cls.get_sr_from_query_params(example_id, run_id, uid)
            except HTTPException as e:
                st.error(repr(e))
                continue

            schema = page_cls.RequestModel.schema(ref_template="{model}")
            for field, model_field in page_cls.RequestModel.__fields__.items():
                if model_field.required:
                    input_fields = required_input_fields
                else:
                    input_fields = optional_input_fields
                field_props = schema["properties"][field]
                title = field_props["title"]
                keys = None
                if is_arr(field_props):
                    try:
                        ref = field_props["items"]["$ref"]
                        props = schema["definitions"][ref]["properties"]
                        keys = {k: prop["title"] for k, prop in props.items()}
                    except KeyError:
                        try:
                            keys = {k: k for k in sr.state[field][0].keys()}
                        except (KeyError, IndexError, AttributeError):
                            pass
                elif field_props.get("type") == "object":
                    try:
                        keys = {k: k for k in sr.state[field].keys()}
                    except (KeyError, AttributeError):
                        pass
                if keys:
                    for k, ktitle in keys.items():
                        input_fields[f"{field}.{k}"] = f"{title}.{ktitle}"
                else:
                    input_fields[field] = title

            schema = page_cls.ResponseModel.schema()
            output_fields |= {
                field: schema["properties"][field]["title"]
                for field, model_field in page_cls.ResponseModel.__fields__.items()
            }

        columns = st.session_state.get(CACHED_COLUMNS, [])
        if not columns:
            return

        for file in files:
            st.data_table(file)

        if not (required_input_fields or optional_input_fields):
            return

        col1, col2 = st.columns(2)

        with col1:
            st.write("##### Input Columns")

            input_columns_old = st.session_state.pop("input_columns", {})
            input_columns_new = st.session_state.setdefault("input_columns", {})

            column_options = [None, *columns]
            for fields in (required_input_fields, optional_input_fields):
                for field, title in fields.items():
                    col = st.selectbox(
                        label="`" + title + "`",
                        options=column_options,
                        key="--input-mapping:" + field,
                        default_value=input_columns_old.get(field),
                    )
                    if col:
                        input_columns_new[field] = col
                st.write("---")

        with col2:
            st.write("##### Output Columns")

            output_columns_old = st.session_state.pop("output_columns", {})
            output_columns_new = st.session_state.setdefault("output_columns", {})

            prev_fields = st.session_state.get("--prev-output-fields")
            fields = {**output_fields, "error_msg": "Error Msg", "run_url": "Run URL"}
            did_change = prev_fields is not None and prev_fields != fields
            st.session_state["--prev-output-fields"] = fields
            for field, title in fields.items():
                col = st.text_input(
                    label="`" + title + "`",
                    key="--output-mapping:" + field,
                    value=output_columns_old.get(field, title if did_change else None),
                )
                if col:
                    output_columns_new[field] = col

    def render_example(self, state: dict):
        render_documents(state)

    def render_output(self):
        files = st.session_state.get("output_documents", [])
        for file in files:
            st.write(file)
            st.data_table(file)

    def run_v2(
        self,
        request: "BulkRunnerPage.RequestModel",
        response: "BulkRunnerPage.ResponseModel",
    ) -> typing.Iterator[str | None]:
        response.output_documents = []

        for doc_ix, doc in enumerate(request.documents):
            df = _read_df(doc)
            in_recs = df.to_dict(orient="records")
            out_recs = []

            f = upload_file_from_bytes(
                filename=f"bulk-runner-{doc_ix}-0-0.csv",
                data=df.to_csv(index=False).encode(),
                content_type="text/csv",
            )
            response.output_documents.append(f)

            df_slices = list(slice_request_df(df, request))
            for slice_ix, (df_ix, arr_len) in enumerate(df_slices):
                rec_ix = len(out_recs)
                out_recs.extend(in_recs[df_ix : df_ix + arr_len])

                for url_ix, f, request_body, page_cls in build_requests_for_df(
                    df, request, df_ix, arr_len
                ):
                    progress = round(
                        (slice_ix + url_ix)
                        / (len(df_slices) + len(request.run_urls))
                        * 100
                    )
                    yield f"{progress}%"

                    example_id, run_id, uid = extract_query_params(f.query.params)
                    sr = page_cls.get_sr_from_query_params(example_id, run_id, uid)

                    result, sr = sr.submit_api_call(
                        current_user=self.request.user, request_body=request_body
                    )
                    result.get(disable_sync_subtasks=False)
                    sr.refresh_from_db()
                    state = sr.to_dict()
                    state["run_url"] = sr.get_app_url()
                    state["error_msg"] = sr.error_msg

                    for field, col in request.output_columns.items():
                        if len(request.run_urls) > 1:
                            col = f"({url_ix + 1}) {col}"
                        out_val = state.get(field)
                        if isinstance(out_val, list):
                            for arr_ix, item in enumerate(out_val):
                                if len(out_recs) <= rec_ix + arr_ix:
                                    out_recs.append({})
                                if isinstance(item, dict):
                                    for key, val in item.items():
                                        out_recs[rec_ix + arr_ix][f"{col}.{key}"] = str(
                                            val
                                        )
                                else:
                                    out_recs[rec_ix + arr_ix][col] = str(item)
                        elif isinstance(out_val, dict):
                            for key, val in out_val.items():
                                if isinstance(val, list):
                                    for arr_ix, item in enumerate(val):
                                        if len(out_recs) <= rec_ix + arr_ix:
                                            out_recs.append({})
                                        out_recs[rec_ix + arr_ix][f"{col}.{key}"] = str(
                                            item
                                        )
                                else:
                                    out_recs[rec_ix][f"{col}.{key}"] = str(val)
                        else:
                            out_recs[rec_ix][col] = str(out_val)

                    out_df = pd.DataFrame.from_records(out_recs)
                    f = upload_file_from_bytes(
                        filename=f"bulk-runner-{doc_ix}-{url_ix}-{df_ix}.csv",
                        data=out_df.to_csv(index=False).encode(),
                        content_type="text/csv",
                    )
                    response.output_documents[doc_ix] = f


def build_requests_for_df(df, request, df_ix, arr_len):
    from daras_ai_v2.all_pages import page_slug_map, normalize_slug

    for url_ix, url in enumerate(request.run_urls):
        f = furl(url)
        slug = f.path.segments[0]
        page_cls = page_slug_map[normalize_slug(slug)]
        schema = page_cls.RequestModel.schema()
        properties = schema["properties"]

        request_body = {}
        for field, col in request.input_columns.items():
            parts = field.split(".")
            field_props = properties.get(parts[0]) or properties.get(parts)
            if is_arr(field_props):
                arr = request_body.setdefault(parts[0], [])
                for arr_ix in range(arr_len):
                    value = df.at[df_ix + arr_ix, col]
                    if len(parts) > 1:
                        if len(arr) <= arr_ix:
                            arr.append({})
                        arr[arr_ix][parts[1]] = value
                    else:
                        if len(arr) <= arr_ix:
                            arr.append(None)
                        arr[arr_ix] = value
            elif len(parts) > 1 and field_props.get("type") == "object":
                obj = request_body.setdefault(parts[0], {})
                obj[parts[1]] = df.at[df_ix, col]
            else:
                request_body[field] = df.at[df_ix, col]
        # for validation
        request_body = page_cls.RequestModel.parse_obj(request_body).dict()

        yield url_ix, f, request_body, page_cls


def slice_request_df(df, request):
    from daras_ai_v2.all_pages import page_slug_map, normalize_slug

    arr_cols = set()
    non_arr_cols = set()
    for url_ix, url in enumerate(request.run_urls):
        f = furl(url)
        slug = f.path.segments[0]
        page_cls = page_slug_map[normalize_slug(slug)]
        schema = page_cls.RequestModel.schema()
        properties = schema["properties"]

        for field, col in request.input_columns.items():
            if is_arr(properties.get(field.split(".")[0])):
                arr_cols.add(col)
            else:
                non_arr_cols.add(col)
    array_df = df[list(arr_cols)]
    non_array_df = df[list(non_arr_cols)]

    df_ix = 0
    while df_ix < len(df):
        arr_len = 1
        while df_ix + arr_len < len(df):
            if (
                not arr_cols
                or array_df.iloc[df_ix + arr_len].isnull().all()
                or not non_array_df.iloc[df_ix + arr_len].isnull().all()
            ):
                break
            arr_len += 1
        yield df_ix, arr_len
        df_ix += arr_len


def is_arr(field_props: dict) -> bool:
    try:
        return field_props["type"] == "array"
    except KeyError:
        for props in field_props.get("anyOf", []):
            if props["type"] == "array":
                return True
    return False


def _read_df(f: str) -> "pd.DataFrame":
    import pandas as pd

    r = requests.get(f)
    r.raise_for_status()
    if f.endswith(".csv"):
        df = pd.read_csv(io.StringIO(r.text))
    elif f.endswith(".xlsx") or f.endswith(".xls"):
        df = pd.read_excel(io.BytesIO(r.content))
    elif f.endswith(".json"):
        df = pd.read_json(io.StringIO(r.text))
    elif f.endswith(".tsv"):
        df = pd.read_csv(io.StringIO(r.text), sep="\t")
    elif f.endswith(".xml"):
        df = pd.read_xml(io.StringIO(r.text))
    else:
        raise ValueError(f"Unsupported file type: {f}")
    return df.dropna(how="all", axis=1).dropna(how="all", axis=0)

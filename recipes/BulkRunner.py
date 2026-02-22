import typing
import uuid

import gooey_gui as gui
from furl import furl
from pydantic import BaseModel, Field

from bots.models import Workflow, SavedRun
from daras_ai.image_input import upload_file_from_bytes
from daras_ai.text_format import format_timedelta
from daras_ai_v2 import icons
from daras_ai_v2 import breadcrumbs
from daras_ai_v2.base import BasePage
from daras_ai_v2.breadcrumbs import get_title_breadcrumbs
from daras_ai_v2.doc_search_settings_widgets import (
    bulk_documents_uploader,
    SUPPORTED_SPREADSHEET_TYPES,
)
from daras_ai_v2.field_render import field_desc, field_title
from daras_ai_v2.functional import map_parallel
from daras_ai_v2.pydantic_validation import HttpUrlStr
from daras_ai_v2.vector_search import (
    download_content_bytes,
    doc_url_to_file_metadata,
    tabular_bytes_to_any_df,
)
from daras_ai_v2.workflow_url_input import (
    url_to_runs,
    init_workflow_selector,
    edit_button,
    del_button,
    workflow_url_input,
    get_published_run_options,
    edit_done_button,
)
from recipes.DocSearch import render_documents

if typing.TYPE_CHECKING:
    import pandas as pd


class BulkRunnerPage(BasePage):
    title = "Bulk Runner"
    explore_image = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/87f35df4-88d7-11ee-aac9-02420a00016b/Bulk%20Runner.png.png"
    workflow = Workflow.BULK_RUNNER
    slug_versions = ["bulk-runner", "bulk"]
    price = 1

    class RequestModel(BasePage.RequestModel):
        documents: list[HttpUrlStr] = Field(
            title="Input Data Spreadsheet",
            description="""
Add a CSV, Excel or Google Sheet url with the columns:
1. **Input prompt** for your questions
2. **Golden Answer** for your ideal output (optional)

TIP: Only the left most Sheet of Excel/Google Sheet is used so add ~3 rows of common QnAs while testing and then add more later to save time and credits.
            """,
        )
        run_urls: list[HttpUrlStr] = Field(
            title="Gooey Workflows",
            description="""
Provide one or more Gooey.AI workflow runs.
Add multiple runs from the same workflow (e.g. two versions of your copilot) and we'll run the inputs through each of them.
            """,
        )

        input_columns: dict[str, str] = Field(
            title="Input Column Mappings",
            description="""
For each input field in the Gooey.AI workflow, specify the column in your input data that corresponds to it.
            """,
        )
        output_columns: dict[str, str] = Field(
            title="Output Column Mappings",
            description="""
For each output field in the Gooey.AI workflow, specify the column name that you'd like to use for it in the output data.
            """,
        )

        eval_urls: list[HttpUrlStr] | None = Field(
            None,
            title="Evaluation Workflows",
            description="""
_(optional)_ Add one or more Gooey.AI Evaluator Workflows to evaluate the results of your runs.
            """,
        )

    class ResponseModel(BaseModel):
        output_documents: list[HttpUrlStr]

        eval_runs: list[HttpUrlStr] | None = Field(
            None,
            title="Evaluation Run URLs",
            description="""
List of URLs to the evaluation runs that you requested.
            """,
        )

    def render_form_v2(self):
        gui.write(
            f"##### {field_title(self.RequestModel, 'run_urls')}",
            help=field_desc(self.RequestModel, "run_urls"),
        )
        run_urls = list_view_editor(
            add_btn_label="Add a Workflow",
            key="run_urls",
            render_inputs=self.render_run_url_inputs,
            flatten_dict_key="url",
        )

        files = bulk_documents_uploader(
            f"##### {field_title(self.RequestModel, 'documents')}",
            help=field_desc(self.RequestModel, "documents"),
            accept=SUPPORTED_SPREADSHEET_TYPES,
        )

        preferred_input_fields = {}
        other_input_fields = {}
        output_fields = {}

        for url in run_urls:
            try:
                page_cls, sr, _ = url_to_runs(url)
            except Exception:
                continue

            schema = page_cls.RequestModel.model_json_schema(ref_template="{model}")
            for field_name, field_info in page_cls.RequestModel.model_fields.items():
                if (
                    field_info.is_required()
                    or field_name in page_cls.get_example_preferred_fields(sr.state)
                ):
                    input_fields = preferred_input_fields
                else:
                    input_fields = other_input_fields
                field_props = schema["properties"][field_name]
                title = field_props.get(
                    "title", field_name.replace("_", " ").capitalize()
                )
                keys = None
                if is_arr(field_props):
                    try:
                        ref = field_props["items"]["$ref"]
                        props = schema["definitions"][ref]["properties"]
                        keys = {k: prop["title"] for k, prop in props.items()}
                    except KeyError:
                        try:
                            keys = {k: k for k in sr.state[field_name][0].keys()}
                        except (KeyError, IndexError, AttributeError, TypeError):
                            pass
                elif is_obj(field_props):
                    try:
                        keys = {k: k for k in sr.state[field_name].keys()}
                    except (KeyError, AttributeError, TypeError):
                        pass

                if keys:
                    for k, ktitle in keys.items():
                        input_fields[f"{field_name}.{k}"] = f"{title}.{ktitle}"
                else:
                    input_fields[field_name] = title

            schema = page_cls.ResponseModel.model_json_schema()
            output_fields |= {
                field: schema["properties"][field]["title"]
                for field in page_cls.ResponseModel.model_fields
            }

        gui.write(
            "###### Input Columns",
            help="""Please select which CSV column corresponds to your workflow's input fields.
To understand what each field represents, check out our [API docs](https://api.gooey.ai/docs).""",
        )

        name_prefix = "input_column:"
        for field, col in gui.session_state.get("input_columns", {}).items():
            gui.session_state.setdefault(name_prefix + col, field)
        for file in files:
            gui.data_table(
                file,
                headerSelect=dict(
                    name=name_prefix + "{col}",
                    options=[
                        dict(value=None, label=gui.BLANK_OPTION),
                    ]
                    + [
                        dict(value=col, label=col)
                        for col in sorted(preferred_input_fields.keys())
                    ]
                    + [
                        dict(value=col, label=col)
                        for col in sorted(other_input_fields.keys())
                    ],
                ),
            )
        gui.newline()
        gui.session_state["input_columns"] = {
            field: col.removeprefix(name_prefix)
            for col, field in gui.session_state.items()
            if col.startswith(name_prefix) and field != gui.BLANK_OPTION
        }

        if not (preferred_input_fields or other_input_fields):
            return

        output_fields = {
            "run_url": "Run URL",
            "run_time": "Run Time",
            "error_msg": "Error Msg",
            "price": "Price",
        } | output_fields
        gui.session_state.setdefault(
            "selected_output_fields",
            list(gui.session_state.get("output_columns", {})),
        )
        selected_output_fields = gui.multiselect(
            "###### Output Columns",
            help="""Please select which fields you'd like to include in the output CSV.
To understand what each field represents, check out our [API docs](https://api.gooey.ai/docs).""",
            options=list(output_fields),
            key="selected_output_fields",
            format_func=output_fields.__getitem__,
            allow_none=True,
        )
        gui.session_state["output_columns"] = {
            field: output_fields.get(field, field) for field in selected_output_fields
        }

        gui.write("---")
        gui.write(
            f"##### {field_title(self.RequestModel, 'eval_urls')}",
            help=field_desc(self.RequestModel, "eval_urls"),
        )
        list_view_editor(
            add_btn_label="Add an Eval",
            key="eval_urls",
            render_inputs=self.render_eval_url_inputs,
            flatten_dict_key="url",
        )

    def render_run_preview_output(self, state: dict):
        render_documents(state)

    def render_output(self):
        eval_runs = gui.session_state.get("eval_runs")

        if eval_runs:
            _backup = gui.session_state
            for url in eval_runs:
                try:
                    page_cls, sr, pr = url_to_runs(url)
                except SavedRun.DoesNotExist:
                    continue
                gui.set_session_state(sr.state)
                title = breadcrumbs.get_title_breadcrumbs(
                    page_cls=page_cls, sr=sr, pr=pr
                ).title_with_prefix()
                gui.html(
                    '<i class="fa fa-external-link"></i>'
                    f' <a href="{url}" target="_blank">{title}</a>'
                )
                try:
                    page_cls().render_output()
                except Exception as e:
                    gui.error(repr(e))
                gui.write("---")
            gui.set_session_state(_backup)
        else:
            files = gui.session_state.get("output_documents", [])
            for file in files:
                gui.html(
                    '<span class="float-end">'
                    '<i class="fa fa-file-csv"></i>'
                    f' <a href="{file}" target="_blank">Download</a>'
                    "</span><br>"
                )
                gui.data_table(file)

    def run_v2(
        self,
        request: "BulkRunnerPage.RequestModel",
        response: "BulkRunnerPage.ResponseModel",
    ) -> typing.Iterator[str | None]:
        import pandas as pd

        response.output_documents = []
        array_columns = set()

        for doc_ix, doc in enumerate(request.documents):
            df = read_df_any(doc)
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

                used_col_names = set()
                for url_ix, request_body, page_cls, sr, pr in build_requests_for_df(
                    df, request, df_ix, arr_len, array_columns
                ):
                    progress = round(
                        (slice_ix + url_ix)
                        / (len(df_slices) + len(request.run_urls))
                        * 100
                    )
                    yield f"{progress}%"

                    result, sr = sr.submit_api_call(
                        workspace=self.current_workspace,
                        current_user=self.request.user,
                        request_body=request_body,
                        parent_pr=pr,
                    )
                    sr.wait_for_celery_result(result)

                    state = sr.to_dict()
                    state["run_url"] = sr.get_app_url()
                    state["price"] = sr.price
                    state["run_time"] = round(sr.run_time.total_seconds(), 2)
                    state["error_msg"] = sr.error_msg

                    for field, col in request.output_columns.items():
                        if len(request.run_urls) > 1:
                            if (
                                pr
                                and pr.title
                                and f"({pr.title}) {col}" not in used_col_names
                            ):
                                col = f"({pr.title}) {col}"
                                used_col_names.add(col)
                            else:
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
                                        array_columns.add(f"{col}.{key}")
                                else:
                                    out_recs[rec_ix + arr_ix][col] = str(item)
                                    array_columns.add(col)
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

        if not request.eval_urls:
            return

        response.eval_runs = []
        for url in request.eval_urls:
            page_cls, sr, pr = url_to_runs(url)
            yield f"Running {get_title_breadcrumbs(page_cls, sr, pr).title_with_prefix()}..."
            request_body = page_cls.RequestModel(
                documents=response.output_documents,
                array_columns=array_columns or None,
            ).model_dump(exclude_unset=True)
            result, sr = sr.submit_api_call(
                workspace=self.current_workspace,
                current_user=self.request.user,
                request_body=request_body,
                parent_pr=pr,
            )
            sr.wait_for_celery_result(result)
            response.eval_runs.append(sr.get_app_url())

    def render_description(self):
        gui.write(
            """
Building complex AI workflows like copilot) and then evaluating each iteration is complex.
Workflows are affected by the particular LLM used (GPT4 vs PalM2), their vector DB knowledge sets (e.g. your google docs), how synthetic data creation happened (e.g. how you transformed your video transcript or PDF into structured data), which translation or speech engine you used and your LLM prompts. Every change can affect the quality of your outputs.

1. This bulk tool enables you to do two incredible things:
2. Upload your own set of inputs (e.g. typical questions to your bot) to any gooey workflow (e.g. /copilot) and run them in bulk to generate outputs or answers.
3. Compare the results of competing workflows to determine which one generates better outputs.

To get started:
1. Enter the Gooey.AI Workflow URLs that you'd like to run in bulk
2. Enter a csv of sample inputs to run in bulk
3. Ensure that the mapping between your inputs and API parameters of the Gooey.AI workflow are correctly mapped.
4. Tap Submit.
5. Wait for results
6. Make a change to your Gooey Workflow, copy its URL and repeat Step 1 (or just add the link to see the results of both workflows together)
        """
        )

    def _render_url_input_only(self, key: str, del_key: str, d: dict, is_mobile: bool):
        columns = [8, 4] if is_mobile else [9, 3]
        col1, col2 = gui.columns(
            columns, responsive=False, style={"--bs-gutter-x": "0.25rem"}
        )

        with col1:
            url = gui.text_input(
                "",
                key=key,
                value=d.get("url"),
                placeholder="https://gooey.ai/.../?run_id=...",
            )

        with col2:
            with gui.div(className="d-flex justify-content-between"):
                edit_done_button(key)
                gui.url_button(url)
                del_button(del_key)

        return url

    def _render_workflow_selector(self, key: str, d: dict):
        from daras_ai_v2.all_pages import all_home_pages

        options = {
            page_cls.workflow: page_cls.get_recipe_short_title()
            for page_cls in all_home_pages
        }
        last_workflow_key = "__last_run_url_workflow"
        workflow = gui.selectbox(
            "",
            key=key + ":workflow",
            value=(d.get("workflow") or gui.session_state.get(last_workflow_key)),
            options=options,
            format_func=lambda x: options[x],
        )
        d["workflow"] = workflow
        # use this to set default for next time
        gui.session_state[last_workflow_key] = workflow
        return workflow

    def _render_url_selector(self, key: str, d: dict, workflow):
        page_cls = Workflow(workflow).page_cls
        url_options = get_published_run_options(
            page_cls, current_user=self.request.user
        )
        url_options.update(d.get("--added_workflows", {}))

        url = gui.selectbox(
            "",
            key=key,
            options=url_options,
            value=d.get("url"),
            format_func=lambda x: url_options[x],
        )
        return url

    def _render_workflow_mode_mobile(self, key: str, del_key: str, d: dict):
        wcol1, wcol2 = gui.columns(
            [8, 4], responsive=False, style={"--bs-gutter-x": "0.25rem"}
        )

        with wcol1:
            with gui.div(className="pt-1"):
                workflow = self._render_workflow_selector(key, d)

        with wcol2:
            with gui.div(className="d-flex justify-content-between"):
                edit_button(key)
                gui.url_button(d.get("url", ""))
                del_button(del_key)

        with gui.div(className="pb-2"):
            url = self._render_url_selector(key, d, workflow)

        return url

    def _render_workflow_mode_desktop(self, key: str, del_key: str, d: dict):
        col1, col2 = gui.columns(
            [9, 3], responsive=False, style={"--bs-gutter-x": "0.25rem"}
        )

        with col1:
            scol1, scol2 = gui.columns(
                [3, 9], responsive=False, style={"--bs-gutter-x": "0.5rem"}
            )

            with scol1:
                with gui.div(className="pt-1"):
                    workflow = self._render_workflow_selector(key, d)

            with scol2:
                with gui.div(className="pt-1"):
                    url = self._render_url_selector(key, d, workflow)

        with col2:
            with gui.div(className="d-flex justify-content-between"):
                edit_button(key)
                gui.url_button(url)
                del_button(del_key)

        return url

    def render_run_url_inputs(self, key: str, del_key: str, d: dict):
        init_workflow_selector(d, key)

        if not d.get("workflow") and d.get("url"):
            with gui.div(className="d-block d-lg-none"):
                url = self._render_url_input_only(key, del_key, d, is_mobile=True)

            with gui.div(className="d-none d-lg-block"):
                url = self._render_url_input_only(key, del_key, d, is_mobile=False)

        else:
            with gui.div(className="d-block d-lg-none"):
                url = self._render_workflow_mode_mobile(key, del_key, d)

            with gui.div(className="d-none d-lg-block"):
                url = self._render_workflow_mode_desktop(key, del_key, d)

        try:
            url_to_runs(url)
        except Exception as e:
            gui.error(repr(e))
        d["url"] = url

    def render_eval_url_inputs(self, key: str, del_key: str | None, d: dict):
        from recipes.BulkEval import BulkEvalPage

        workflow_url_input(
            page_cls=BulkEvalPage,
            key=key,
            internal_state=d,
            del_key=del_key,
            current_user=self.request.user,
        )


def build_requests_for_df(df, request, df_ix, arr_len, array_columns):
    for url_ix, url in enumerate(request.run_urls):
        page_cls, sr, pr = url_to_runs(url)
        schema = page_cls.RequestModel.model_json_schema()
        properties = schema["properties"]

        request_body = {}
        for field, col in request.input_columns.items():
            if col not in df.columns:
                continue
            parts = field.split(".")
            field_props = properties.get(parts[0]) or properties.get(field)
            if is_arr(field_props):
                array_columns.add(col)
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
            elif len(parts) > 1 and is_obj(field_props):
                obj = request_body.setdefault(parts[0], sr.state.get(parts[0], {}))
                obj[parts[1]] = df.at[df_ix, col]
            else:
                request_body[field] = df.at[df_ix, col]
        # for validation
        request_body = page_cls.RequestModel.model_validate(request_body).model_dump(
            exclude_unset=True
        )

        yield url_ix, request_body, page_cls, sr, pr


def slice_request_df(df, request):
    from daras_ai_v2.all_pages import page_slug_map, normalize_slug

    arr_cols = set()
    non_arr_cols = set()
    for url_ix, url in enumerate(request.run_urls):
        f = furl(url)
        slug = f.path.segments[0]
        page_cls = page_slug_map[normalize_slug(slug)]
        schema = page_cls.RequestModel.model_json_schema()
        properties = schema["properties"]

        for field, col in request.input_columns.items():
            if col not in df.columns:
                continue
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
                or not all(array_df.iloc[df_ix + arr_len])
                or any(non_array_df.iloc[df_ix + arr_len])
            ):
                break
            arr_len += 1
        yield df_ix, arr_len
        df_ix += arr_len


def is_arr(field_props: dict | None) -> bool:
    if not field_props:
        return False
    try:
        return field_props["type"] == "array"
    except KeyError:
        for props in field_props.get("anyOf", []):
            if props.get("type") == "array":
                return True
    return False


def is_obj(field_props: dict | None) -> bool:
    if not field_props:
        return False
    try:
        return field_props["type"] == "object"
    except KeyError:
        pass
    try:
        return field_props["$ref"]
    except KeyError:
        pass
    for props in field_props.get("anyOf", []):
        if props.get("type") == "object":
            return True
    return False


@gui.cache_in_session_state
def get_columns(files: list[str]) -> list[str]:
    try:
        dfs = map_parallel(read_df_any, files)
    except ValueError:
        return []
    return list(
        {
            col: None
            for df in dfs
            for col in df.columns
            if not col.startswith("Unnamed:")
        }
    )


def read_df_any(f_url: str) -> "pd.DataFrame":
    file_meta = doc_url_to_file_metadata(f_url)
    f_bytes, mime_type = download_content_bytes(
        f_url=f_url, mime_type=file_meta.mime_type, export_links=file_meta.export_links
    )
    df = tabular_bytes_to_any_df(
        f_name=file_meta.name, f_bytes=f_bytes, mime_type=mime_type
    )
    # Drop completely empty rows/columns, fill NaNs, and reset the index so that it is contiguous
    return (
        df.dropna(how="all", axis=1)
        .dropna(how="all", axis=0)
        .fillna("")
        .reset_index(drop=True)
    )


def list_view_editor(
    *,
    add_btn_label: str = None,
    add_btn_type: str = "secondary",
    key: str,
    render_labels: typing.Callable = None,
    render_inputs: typing.Callable[[str, str, dict], None],
    flatten_dict_key: str = None,
):
    if flatten_dict_key:
        list_key = f"--list-view:{key}"
        gui.session_state.setdefault(
            list_key,
            [{flatten_dict_key: val} for val in gui.session_state.get(key, [])],
        )
        new_lst = list_view_editor(
            add_btn_label=add_btn_label,
            key=list_key,
            render_labels=render_labels,
            render_inputs=render_inputs,
        )
        ret = [d[flatten_dict_key] for d in new_lst]
        gui.session_state[key] = ret
        return ret

    old_lst = gui.session_state.get(key) or []
    add_key = f"--{key}:add"
    if gui.session_state.get(add_key):
        old_lst.append({})
    label_placeholder = gui.div()
    new_lst = []
    for d in old_lst:
        entry_key = d.setdefault("__key__", f"--{key}:{uuid.uuid1()}")
        del_key = entry_key + ":del"
        if gui.session_state.pop(del_key, None):
            continue
        render_inputs(entry_key, del_key, d)
        new_lst.append(d)
    if new_lst and render_labels:
        with label_placeholder:
            render_labels()
    gui.session_state[key] = new_lst
    if add_btn_label:
        with gui.center():
            gui.button(f"{icons.add} {add_btn_label}", key=add_key, type=add_btn_type)
    return new_lst

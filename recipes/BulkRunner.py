import datetime
import typing
import uuid

from furl import furl
from pydantic import BaseModel, Field

import gooey_gui as gui
from bots.models import Workflow, SavedRun
from daras_ai.image_input import upload_file_from_bytes
from daras_ai_v2 import icons
from daras_ai_v2.base import BasePage
from daras_ai_v2.breadcrumbs import get_title_breadcrumbs
from daras_ai_v2.doc_search_settings_widgets import (
    bulk_documents_uploader,
    SUPPORTED_SPREADSHEET_TYPES,
)
from daras_ai_v2.field_render import field_title_desc
from daras_ai_v2.functional import map_parallel
from daras_ai_v2.pydantic_validation import FieldHttpUrl
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
from gooeysite.bg_db_conn import get_celery_result_db_safe
from recipes.DocSearch import render_documents

DEFAULT_BULK_META_IMG = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/d80fd4d8-93fa-11ee-bc13-02420a0001cc/Bulk%20Runner.jpg.png"


class BulkRunnerPage(BasePage):
    title = "Bulk Runner"
    explore_image = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/87f35df4-88d7-11ee-aac9-02420a00016b/Bulk%20Runner.png.png"
    workflow = Workflow.BULK_RUNNER
    slug_versions = ["bulk-runner", "bulk"]
    price = 1

    class RequestModel(BasePage.RequestModel):
        documents: list[FieldHttpUrl] = Field(
            title="Input Data Spreadsheet",
            description="""
Upload or link to a CSV or google sheet that contains your sample input data.
For example, for Copilot, this would sample questions or for Art QR Code, would would be pairs of image descriptions and URLs.
Remember to includes header names in your CSV too.
            """,
        )
        run_urls: list[FieldHttpUrl] = Field(
            title="Gooey Workflows",
            description="""
Provide one or more Gooey.AI workflow runs.
You can add multiple runs from the same recipe (e.g. two versions of your copilot) and we'll run the inputs over both of them.
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

        eval_urls: list[FieldHttpUrl] | None = Field(
            title="Evaluation Workflows",
            description="""
_(optional)_ Add one or more Gooey.AI Evaluator Workflows to evaluate the results of your runs.
            """,
        )

    class ResponseModel(BaseModel):
        output_documents: list[FieldHttpUrl]

        eval_runs: list[FieldHttpUrl] | None = Field(
            title="Evaluation Run URLs",
            description="""
List of URLs to the evaluation runs that you requested.
            """,
        )

    def preview_image(self, state: dict) -> str | None:
        return DEFAULT_BULK_META_IMG

    def render_form_v2(self):
        gui.write(f"##### {field_title_desc(self.RequestModel, 'run_urls')}")
        run_urls = list_view_editor(
            add_btn_label="Add a Workflow",
            key="run_urls",
            render_inputs=self.render_run_url_inputs,
            flatten_dict_key="url",
        )

        files = bulk_documents_uploader(
            f"---\n##### {field_title_desc(self.RequestModel, 'documents')}",
            accept=SUPPORTED_SPREADSHEET_TYPES,
        )

        required_input_fields = {}
        optional_input_fields = {}
        output_fields = {}

        for url in run_urls:
            try:
                page_cls, sr, _ = url_to_runs(url)
            except:
                continue

            schema = page_cls.RequestModel.schema(ref_template="{model}")
            for field, model_field in page_cls.RequestModel.__fields__.items():
                if model_field.required:
                    input_fields = required_input_fields
                else:
                    input_fields = optional_input_fields
                field_props = schema["properties"][field]
                title = field_props.get("title", field.replace("_", " ").capitalize())
                keys = None
                if is_arr(field_props):
                    try:
                        ref = field_props["items"]["$ref"]
                        props = schema["definitions"][ref]["properties"]
                        keys = {k: prop["title"] for k, prop in props.items()}
                    except KeyError:
                        try:
                            keys = {k: k for k in sr.state[field][0].keys()}
                        except (KeyError, IndexError, AttributeError, TypeError):
                            pass
                elif is_obj(field_props):
                    try:
                        keys = {k: k for k in sr.state[field].keys()}
                    except (KeyError, AttributeError, TypeError):
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

        gui.write(
            """
###### **Preview**: Here's what you uploaded
            """
        )
        for file in files:
            gui.data_table(file)

        if not (required_input_fields or optional_input_fields):
            return

        with gui.div(className="pt-3"):
            gui.write(
                """
###### **Columns**
Please select which CSV column corresponds to your workflow's input fields.
For the outputs, select the fields that should be included in the output CSV.
To understand what each field represents, check out our [API docs](https://api.gooey.ai/docs).
                """,
            )

        visible_col1, visible_col2 = gui.columns(2)
        with gui.expander("🤲 Show All Columns"):
            hidden_col1, hidden_col2 = gui.columns(2)

        with visible_col1:
            gui.write("##### Inputs")
        with hidden_col1:
            gui.write("##### Inputs")

        input_columns_old = gui.session_state.pop("input_columns", {})
        input_columns_new = gui.session_state.setdefault("input_columns", {})

        column_options = [None, *get_columns(files)]
        for fields, div in (
            (required_input_fields, visible_col1),
            (optional_input_fields, hidden_col1),
        ):
            for field, title in fields.items():
                with div:
                    col = gui.selectbox(
                        label="`" + title + "`",
                        options=column_options,
                        key="--input-mapping:" + field,
                        value=input_columns_old.get(field),
                    )
                if col:
                    input_columns_new[field] = col

        with visible_col2:
            gui.write("##### Outputs")
        with hidden_col2:
            gui.write("##### Outputs")

        visible_out_fields = {}
        # only show the first output & run url field by default, and hide others
        if output_fields:
            try:
                first_out_field = next(
                    field for field in output_fields if "output" in field
                )
            except StopIteration:
                first_out_field = next(iter(output_fields))
            visible_out_fields[first_out_field] = output_fields[first_out_field]
        visible_out_fields["run_url"] = "Run URL"

        hidden_out_fields = {
            "price": "Price",
            "run_time": "Run Time",
            "error_msg": "Error Msg",
        } | {k: v for k, v in output_fields.items() if k not in visible_out_fields}

        output_columns_old = gui.session_state.pop("output_columns", {})
        output_columns_new = gui.session_state.setdefault("output_columns", {})

        for fields, div, checked in (
            (visible_out_fields, visible_col2, True),
            (hidden_out_fields, hidden_col2, False),
        ):
            for field, title in fields.items():
                with div:
                    col = gui.checkbox(
                        label="`" + title + "`",
                        key="--output-mapping:" + field,
                        value=bool(output_columns_old.get(field, checked)),
                    )
                if col:
                    output_columns_new[field] = title

        gui.write("---")
        gui.write(f"##### {field_title_desc(self.RequestModel, 'eval_urls')}")
        list_view_editor(
            add_btn_label="Add an Eval",
            key="eval_urls",
            render_inputs=self.render_eval_url_inputs,
            flatten_dict_key="url",
        )

    def render_example(self, state: dict):
        render_documents(state)

    def render_output(self):
        eval_runs = gui.session_state.get("eval_runs")

        if eval_runs:
            _backup = gui.session_state
            for url in eval_runs:
                try:
                    page_cls, sr, _ = url_to_runs(url)
                except SavedRun.DoesNotExist:
                    continue
                gui.set_session_state(sr.state)
                try:
                    page_cls().render_output()
                except Exception as e:
                    gui.error(repr(e))
                gui.write(url)
                gui.write("---")
            gui.set_session_state(_backup)
        else:
            files = gui.session_state.get("output_documents", [])
            for file in files:
                gui.write(file)
                gui.data_table(file)

    def run_v2(
        self,
        request: "BulkRunnerPage.RequestModel",
        response: "BulkRunnerPage.ResponseModel",
    ) -> typing.Iterator[str | None]:
        import pandas as pd

        response.output_documents = []

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
                    df, request, df_ix, arr_len
                ):
                    progress = round(
                        (slice_ix + url_ix)
                        / (len(df_slices) + len(request.run_urls))
                        * 100
                    )
                    yield f"{progress}%"

                    result, sr = sr.submit_api_call(
                        current_user=self.request.user,
                        request_body=request_body,
                        parent_pr=pr,
                    )
                    get_celery_result_db_safe(result)
                    sr.refresh_from_db()

                    run_time = datetime.timedelta(
                        seconds=int(sr.run_time.total_seconds())
                    )
                    state = sr.to_dict()
                    state["run_url"] = sr.get_app_url()
                    state["price"] = sr.price
                    state["run_time"] = str(run_time)
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

        if not request.eval_urls:
            return

        response.eval_runs = []
        for url in request.eval_urls:
            page_cls, sr, pr = url_to_runs(url)
            yield f"Running {get_title_breadcrumbs(page_cls, sr, pr).h1_title}..."
            request_body = page_cls.RequestModel(
                documents=response.output_documents
            ).dict(exclude_unset=True)
            result, sr = sr.submit_api_call(
                current_user=self.request.user, request_body=request_body, parent_pr=pr
            )
            get_celery_result_db_safe(result)
            sr.refresh_from_db()
            response.eval_runs.append(sr.get_app_url())

    def preview_description(self, state: dict) -> str:
        return """
Which AI model actually works best for your needs?
Upload your own data and evaluate any Gooey.AI workflow, LLM or AI model against any other.
Great for large data sets, AI model evaluation, task automation, parallel processing and automated testing.
To get started, paste in a Gooey.AI workflow, upload a CSV of your test data (with header names!), check the mapping of headers to workflow inputs and tap Submit.
More tips in the Details below.
        """

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

    def render_run_url_inputs(self, key: str, del_key: str, d: dict):
        from daras_ai_v2.all_pages import all_home_pages

        init_workflow_selector(d, key)

        col1, col2, col3, col4 = gui.columns([9, 1, 1, 1], responsive=False)
        if not d.get("workflow") and d.get("url"):
            with col1:
                url = gui.text_input(
                    "",
                    key=key,
                    value=d.get("url"),
                    placeholder="https://gooey.ai/.../?run_id=...",
                )
            with col2:
                edit_done_button(key)
        else:
            with col1:
                scol1, scol2 = gui.columns([1, 1], responsive=False)
            with scol1:
                with gui.div(className="pt-1"):
                    options = {
                        page_cls.workflow: page_cls.get_recipe_title()
                        for page_cls in all_home_pages
                    }
                    last_workflow_key = "__last_run_url_workflow"
                    workflow = gui.selectbox(
                        "",
                        key=key + ":workflow",
                        value=(
                            d.get("workflow")
                            or gui.session_state.get(last_workflow_key)
                        ),
                        options=options,
                        format_func=lambda x: options[x],
                    )
                    d["workflow"] = workflow
                    # use this to set default for next time
                    gui.session_state[last_workflow_key] = workflow
            with scol2:
                page_cls = Workflow(workflow).page_cls
                options = get_published_run_options(
                    page_cls, current_user=self.request.user
                )
                options.update(d.get("--added_workflows", {}))
                with gui.div(className="pt-1"):
                    url = gui.selectbox(
                        "",
                        key=key,
                        options=options,
                        value=d.get("url"),
                        format_func=lambda x: options[x],
                    )
            with col2:
                edit_button(key)
        with col3:
            gui.url_button(url)
        with col4:
            del_button(del_key)

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


def build_requests_for_df(df, request, df_ix, arr_len):
    for url_ix, url in enumerate(request.run_urls):
        page_cls, sr, pr = url_to_runs(url)
        schema = page_cls.RequestModel.schema()
        properties = schema["properties"]

        request_body = {}
        for field, col in request.input_columns.items():
            parts = field.split(".")
            field_props = properties.get(parts[0]) or properties.get(field)
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
            elif len(parts) > 1 and is_obj(field_props):
                obj = request_body.setdefault(parts[0], sr.state.get(parts[0], {}))
                obj[parts[1]] = df.at[df_ix, col]
            else:
                request_body[field] = df.at[df_ix, col]
        # for validation
        request_body = page_cls.RequestModel.parse_obj(request_body).dict(
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
            if props["type"] == "array":
                return True
    return False


def is_obj(field_props: dict | None) -> bool:
    if not field_props:
        return False
    return bool(field_props.get("type") == "object" or field_props.get("$ref"))


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
        f_url=f_url, mime_type=file_meta.mime_type
    )
    df = tabular_bytes_to_any_df(
        f_name=file_meta.name, f_bytes=f_bytes, mime_type=mime_type
    )
    return df.dropna(how="all", axis=1).dropna(how="all", axis=0).fillna("")


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

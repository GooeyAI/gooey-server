import itertools
import json
import os
import typing
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
from itertools import zip_longest

import typing_extensions
from pydantic import BaseModel, Field

import gooey_gui as gui
from bots.models import Workflow
from daras_ai.image_input import upload_file_from_bytes
from daras_ai_v2.base import BasePage
from daras_ai_v2.doc_search_settings_widgets import (
    bulk_documents_uploader,
    SUPPORTED_SPREADSHEET_TYPES,
)
from daras_ai_v2.field_render import field_title_desc
from daras_ai_v2.functional import map_parallel
from daras_ai_v2.language_model import (
    run_language_model,
    LargeLanguageModels,
)
from daras_ai_v2.language_model_settings_widgets import LanguageModelSettings
from daras_ai_v2.variables_widget import render_prompt_vars
from recipes.BulkRunner import read_df_any, list_view_editor, del_button
from recipes.DocSearch import render_documents

NROWS_CACHE_KEY = "__nrows"

AggFunctionsList = [
    "mean",
    "median",
    "min",
    "max",
    "sum",
    "cumsum",
    "prod",
    "cumprod",
    "std",
    "var",
    "first",
    "last",
    "count",
    "cumcount",
    "nunique",
    "rank",
]


class EvalPrompt(typing.TypedDict):
    name: str
    prompt: str


class AggFunction(typing_extensions.TypedDict):
    column: typing_extensions.NotRequired[str]
    function: typing.Literal[tuple(AggFunctionsList)]


class AggFunctionResult(typing.TypedDict):
    column: str
    function: typing.Literal[tuple(AggFunctionsList)]
    count: int
    value: float


def remove_common_prefix_suffix(a: list[str]) -> list[str]:
    if not a:
        return a
    prefix = len(os.path.commonprefix(a)) or 0
    suffix = -len(os.path.commonprefix([s[::-1] for s in a])) or None
    ret = [s[prefix:suffix] for s in a]
    if not all(ret) or all(s.isdigit() for s in ret):
        return a
    return ret


def _render_results(results: list[AggFunctionResult]):
    import plotly.graph_objects as go
    from plotly.colors import sample_colorscale

    for k, g in itertools.groupby(results, key=lambda d: d["function"]):
        gui.write("---\n###### **Aggregate**: " + k.capitalize())

        g = list(g)

        columns = remove_common_prefix_suffix([d["column"] for d in g])
        values = [round(d["value"] or 0, 2) for d in g]

        norm_values = [
            (v - min(values)) / ((max(values) - min(values)) or 1) for v in values
        ]
        colors = sample_colorscale("RdYlGn", norm_values, colortype="tuple")
        colors = [f"rgba{(r * 255, g * 255, b * 255, 0.5)}" for r, g, b in colors]

        gui.data_table(
            [
                ["Metric", k.capitalize(), "Count"],
            ]
            + [
                [
                    columns[i],
                    dict(
                        kind="number",
                        readonly=True,
                        displayData=str(values[i]),
                        data=values[i],
                        themeOverride=dict(bgCell=colors[i]),
                    ),
                    g[i].get("count", 1),
                ]
                for i in range(len(g))
            ]
        )

        fig = go.Figure(
            data=[
                go.Bar(
                    name=k,
                    x=columns,
                    y=values,
                    marker=dict(color=colors),
                    text=values,
                    texttemplate="<b>%{text}</b>",
                    insidetextanchor="middle",
                    insidetextfont=dict(size=24),
                ),
            ],
            layout=dict(
                margin=dict(l=0, r=0, t=24, b=0),
            ),
        )
        gui.plotly_chart(fig)


class BulkEvalPage(BasePage):
    title = "Evaluator"
    workflow = Workflow.BULK_EVAL
    slug_versions = ["bulk-eval", "eval"]

    explore_image = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/aad314f0-9a97-11ee-8318-02420a0001c7/W.I.9.png.png"

    split_output_tab = True

    def render_description(self):
        gui.write(
            """
Summarize and score every row of any CSV, google sheet or excel with GPT4 (or any LLM you choose).  Then average every score in any column to generate automated evaluations.
            """
        )

    def related_workflows(self) -> list:
        from recipes.BulkRunner import BulkRunnerPage
        from recipes.VideoBots import VideoBotsPage
        from recipes.asr_page import AsrPage
        from recipes.DocSearch import DocSearchPage

        return [BulkRunnerPage, VideoBotsPage, AsrPage, DocSearchPage]

    class RequestModelBase(BasePage.RequestModel):
        documents: list[str] = Field(
            title="Input Data Spreadsheet",
            description="""
Upload or link to a CSV or google sheet that contains your sample input data. 
For example, for Copilot, this would sample questions or for Art QR Code, would would be pairs of image descriptions and URLs. 
Remember to includes header names in your CSV too.
            """,
        )

        eval_prompts: list[EvalPrompt] | None = Field(
            title="Evaluation Prompts",
            description="""
Specify custom LLM prompts to calculate metrics that evaluate each row of the input data. The output should be a JSON object mapping the metric names to values.  
_The `columns` dictionary can be used to reference the spreadsheet columns._            
            """,
        )

        agg_functions: list[AggFunction] | None = Field(
            title="Aggregations",
            description="""
Aggregate using one or more operations. Uses [pandas](https://pandas.pydata.org/pandas-docs/stable/reference/groupby.html#dataframegroupby-computations-descriptive-stats).
            """,
        )

        selected_model: typing.Literal[
            tuple(e.name for e in LargeLanguageModels if e.supports_json)
        ] = LargeLanguageModels.gpt_4_turbo.name

    class RequestModel(LanguageModelSettings, RequestModelBase):
        pass

    class ResponseModel(BaseModel):
        output_documents: list[str]
        final_prompts: list[list[str]] | None
        aggregations: list[list[AggFunctionResult]] | None

    def render_form_v2(self):
        files = bulk_documents_uploader(
            f"##### {field_title_desc(self.RequestModel, 'documents')}",
            accept=SUPPORTED_SPREADSHEET_TYPES,
        )
        gui.session_state[NROWS_CACHE_KEY] = get_nrows(files)
        if not files:
            return

        gui.write(
            """
##### Input Data Preview
Here's what you uploaded:          
            """
        )
        for file in files:
            gui.data_table(file)
        gui.write("---")

        def render_inputs(key: str, del_key: str, d: EvalPrompt):
            col1, col2 = gui.columns([8, 1], responsive=False)
            with col1:
                d["name"] = gui.text_input(
                    label="",
                    label_visibility="collapsed",
                    placeholder="Metric Name",
                    key=key + ":name",
                    value=d.get("name"),
                ).strip()
                d["prompt"] = gui.text_area(
                    label="",
                    label_visibility="collapsed",
                    placeholder="Prompt",
                    key=key + ":prompt",
                    value=d.get("prompt"),
                    height=500,
                ).strip()
            with col2:
                del_button(del_key)

        gui.selectbox(
            "##### Language Model",
            options=[e.name for e in LargeLanguageModels if e.supports_json],
            key="selected_model",
            format_func=lambda e: LargeLanguageModels[e].value,
        )

        gui.write("##### " + field_title_desc(self.RequestModel, "eval_prompts"))
        list_view_editor(
            add_btn_label="Add a Prompt",
            key="eval_prompts",
            render_inputs=render_inputs,
        )

        def render_agg_inputs(key: str, del_key: str, d: AggFunction):
            col1, col3 = gui.columns([8, 1], responsive=False)
            with col1:
                with gui.div(className="pt-1"):
                    d["function"] = gui.selectbox(
                        "",
                        label_visibility="collapsed",
                        key=key + ":func",
                        options=AggFunctionsList,
                        value=d.get("function"),
                    )
            with col3:
                del_button(del_key)

        gui.html("<br>")
        gui.write("##### " + field_title_desc(self.RequestModel, "agg_functions"))
        list_view_editor(
            add_btn_label="Add an Aggregation",
            key="agg_functions",
            render_inputs=render_agg_inputs,
        )

    # def render_settings(self):
    #     language_model_settings()

    def render_run_preview_output(self, state: dict):
        render_documents(state)

    def render_output(self):
        files = gui.session_state.get("output_documents", [])
        aggregations = gui.session_state.get("aggregations", [])

        for file, results in zip_longest(files, aggregations):
            gui.write(file)
            gui.data_table(file)

            if not results:
                continue

            _render_results(results)

    def run_v2(
        self,
        request: "BulkEvalPage.RequestModel",
        response: "BulkEvalPage.ResponseModel",
    ) -> typing.Iterator[str | None]:
        response.output_documents = []
        response.final_prompts = []
        response.aggregations = []

        with ThreadPoolExecutor(max_workers=4) as pool:
            futs = submit(pool, request, response)
            yield from iterate(futs, request, response)

    def fields_to_save(self) -> [str]:
        return super().fields_to_save() + [NROWS_CACHE_KEY]

    def get_raw_price(self, state: dict) -> float:
        try:
            price = LargeLanguageModels[state["selected_model"]].price
        except KeyError:
            price = 1
        nprompts = len(state.get("eval_prompts") or {}) or 1
        nrows = (
            state.get(NROWS_CACHE_KEY) or get_nrows(state.get("documents") or []) or 1
        )
        return price * nprompts * nrows

    def render_steps(self):
        documents = gui.session_state.get("documents") or []
        final_prompts = gui.session_state.get("final_prompts") or []
        for doc, prompts in zip_longest(documents, final_prompts):
            if not prompts:
                continue
            gui.write(f"###### {doc}")
            for i, prompt in enumerate(prompts):
                gui.text_area("", value=prompt, key=f"--final-prompt-{i}")


class TaskResult(typing.NamedTuple):
    llm_output: dict
    doc_ix: int
    current_rec: dict
    out_df_recs: list[dict]
    ep: EvalPrompt


def submit(
    pool: ThreadPoolExecutor,
    request: BulkEvalPage.RequestModel,
    response: BulkEvalPage.ResponseModel,
) -> list[Future[TaskResult]]:
    futs = []
    for doc_ix, doc in enumerate(request.documents):
        response.output_documents.append(doc)
        response.final_prompts.append([])
        response.aggregations.append([])
        df = read_df_any(doc)
        out_df_recs = []
        for current_rec in df.to_dict(orient="records"):
            out_df_recs.append(current_rec)
            for ep_ix, ep in enumerate(request.eval_prompts):
                prompt = render_prompt_vars(
                    ep["prompt"],
                    gui.session_state | {"columns": current_rec},
                )
                response.final_prompts[doc_ix].append(prompt)
                futs.append(
                    pool.submit(
                        _run_language_model,
                        model=LargeLanguageModels[request.selected_model],
                        prompt=prompt,
                        result=TaskResult(
                            llm_output={},
                            doc_ix=doc_ix,
                            current_rec=current_rec,
                            out_df_recs=out_df_recs,
                            ep=ep,
                        ),
                    ),
                )
    return futs


def _run_language_model(model: LargeLanguageModels, prompt: str, result: TaskResult):
    ret = json.loads(
        run_language_model(
            model=model.name,
            prompt=prompt,
            response_format_type="json_object",
        )[0]
    )
    assert isinstance(ret, dict)
    result.llm_output.update(ret)
    return result


def iterate(
    futs: list[Future[TaskResult]],
    request: BulkEvalPage.RequestModel,
    response: BulkEvalPage.ResponseModel,
):
    import pandas as pd

    yield f"Running Evals (1/{len(futs)})..."

    for i, fut in enumerate(as_completed(futs)):
        if i + 1 < len(futs):
            yield f"Running Evals ({i + 2}/{len(futs)})..."
        else:
            yield "Uploading Results..."

        result = fut.result()

        for metric_name, metric_value in result.llm_output.items():
            col = f"{result.ep['name']} - {metric_name}"
            result.current_rec[col] = metric_value

        out_df = pd.DataFrame.from_records(result.out_df_recs)
        f = upload_file_from_bytes(
            filename=f"evaluator-{i + 1}.csv",
            data=out_df.to_csv(index=False).encode(),
            content_type="text/csv",
        )
        response.output_documents[result.doc_ix] = f

        aggs = []
        for agg in request.agg_functions:
            if agg.get("column"):
                cols = [agg["column"]]
            else:
                cols = out_df.select_dtypes(include=["float", "int"]).columns
            for col in cols:
                col_values = out_df[col].dropna()
                agg_value = col_values.agg(agg["function"])
                aggs.append(
                    {
                        "column": col,
                        "function": agg["function"],
                        "count": len(col_values),
                        "value": agg_value,
                    }
                )
        response.aggregations[result.doc_ix] = aggs


@gui.cache_in_session_state
def get_nrows(files: list[str]) -> int:
    try:
        dfs = map_parallel(read_df_any, files)
    except ValueError:
        return 0
    return sum((len(df) for df in dfs), 0)

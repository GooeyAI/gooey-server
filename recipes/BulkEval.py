import json
import itertools
import os
import re
import typing
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
from itertools import zip_longest

import gooey_gui as gui
import typing_extensions
from pydantic import BaseModel, Field

from ai_models.models import AIModelSpec
from bots.models import Workflow
from daras_ai.image_input import upload_file_from_bytes
from daras_ai_v2.base import BasePage
from daras_ai_v2.doc_search_settings_widgets import (
    bulk_documents_uploader,
    SUPPORTED_SPREADSHEET_TYPES,
)
from daras_ai_v2.exceptions import UserError
from daras_ai_v2.field_render import field_title, field_desc
from daras_ai_v2.functional import map_parallel
from daras_ai_v2.language_model import run_language_model
from daras_ai_v2.language_model_settings_widgets import LanguageModelSettings
from daras_ai_v2.variables_widget import render_prompt_vars
from functions.base_llm_tool import BaseLLMTool
from recipes.BulkRunner import read_df_any, list_view_editor, del_button
from recipes.DocSearch import render_documents

if typing.TYPE_CHECKING:
    import pandas as pd

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


class CandidateEvalSpec(typing_extensions.TypedDict):
    output_columns: list[str]
    workflow_title_by_candidate: dict[str, str]


class CandidateEvaluationTool(BaseLLMTool):
    def __init__(self, output_column_names: list[str], candidate_labels: list[str]):
        super().__init__(
            name="submit_evaluation",
            label="Submit Evaluation",
            description=(
                "Score only the workflow output columns requested by the evaluation "
                "prompt. When no columns are named, score evaluation-worthy fields "
                "such as Output Text or Run Time, not metadata such as Price, Run URL, "
                "or Error Message. Return one numeric score for every candidate in each "
                "scored column, using the provided column and candidate names exactly. "
                "Put rationales, best candidates, and other row-level outputs in "
                "summaries."
            ),
            properties={
                "scores": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": len(output_column_names),
                    "items": {
                        "type": "object",
                        "properties": {
                            "column": {
                                "type": "string",
                                "enum": output_column_names,
                            },
                            "candidates": {
                                "type": "array",
                                "minItems": len(candidate_labels),
                                "maxItems": len(candidate_labels),
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "candidate": {
                                            "type": "string",
                                            "enum": candidate_labels,
                                        },
                                        "score": {"type": "number"},
                                    },
                                    "required": ["candidate", "score"],
                                    "additionalProperties": False,
                                },
                            },
                        },
                        "required": ["column", "candidates"],
                        "additionalProperties": False,
                    },
                },
                "summaries": {
                    "type": "array",
                    "description": (
                        "Additional row-level outputs requested by the prompt, such as "
                        "a rationale or the best candidate. Return an empty array when "
                        "none were requested."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "column": {"type": "string"},
                            "value": {"type": "string"},
                        },
                        "required": ["column", "value"],
                        "additionalProperties": False,
                    },
                },
            },
            required=["scores"],
        )

    @property
    def spec_parameters(self) -> dict:
        return super().spec_parameters | {"additionalProperties": False}


class EvalPrompt(typing_extensions.TypedDict):
    name: str
    prompt: str
    candidate_spec: typing_extensions.NotRequired[CandidateEvalSpec]


class AggFunction(typing_extensions.TypedDict):
    column: typing_extensions.NotRequired[str]
    function: typing.Literal[tuple(AggFunctionsList)]


class AggFunctionResult(typing_extensions.TypedDict):
    column: str
    function: typing.Literal[tuple(AggFunctionsList)]
    count: int
    value: float
    eval_prompt_name: typing_extensions.NotRequired[str]
    lower_is_better: typing_extensions.NotRequired[bool]


def remove_common_prefix_suffix(a: list[str]) -> list[str]:
    if not a:
        return a
    prefix = _common_affix_at_boundary(a)
    suffix = _common_affix_at_boundary(a, reverse=True)
    ret = [s.removeprefix(prefix).removesuffix(suffix) for s in a]
    if not all(ret) or all(s.isdigit() for s in ret):
        return a
    return ret


def _common_affix_at_boundary(values: list[str], reverse: bool = False) -> str:
    text = os.path.commonprefix([s[::-1] if reverse else s for s in values])
    if reverse:
        text = text[::-1]
    indexes = range(len(text)) if reverse else range(len(text) - 1, -1, -1)
    for i in indexes:
        if not text[i].isalnum():
            return text[i:] if reverse else text[: i + 1]
    return ""


def _render_results(results: list[AggFunctionResult]):
    import plotly.graph_objects as go
    from plotly.colors import sample_colorscale

    for k, g in itertools.groupby(results, key=lambda d: d["function"]):
        g = list(g)
        eval_prompt_name = g[0].get("eval_prompt_name") or ""
        aggregate_heading = f"Aggregate:{k.capitalize()}"
        heading = aggregate_heading
        if eval_prompt_name:
            heading = f"{eval_prompt_name} {heading}"
        gui.write("---\n###### **" + heading + "**")
        lower_is_better = bool(g[0].get("lower_is_better"))

        columns = remove_common_prefix_suffix([d["column"] for d in g])
        values = [round(d["value"] or 0, 2) for d in g]

        norm_values = [
            (v - min(values)) / ((max(values) - min(values)) or 1) for v in values
        ]
        if lower_is_better:
            norm_values = [1 - v for v in norm_values]
        colors = sample_colorscale("RdYlGn", norm_values, colortype="tuple")
        colors = [f"rgba{(r * 255, g * 255, b * 255, 0.5)}" for r, g, b in colors]

        gui.data_table(
            [
                ["Metric", k.capitalize(), "Count"],
            ]
            + [
                [
                    columns[i],
                    dict(value=values[i], style=dict(backgroundColor=colors[i])),
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
        with gui.div(className="d-flex flex-column align-items-center"):
            gui.plotly_chart(fig)
            if eval_prompt_name:
                gui.caption(eval_prompt_name, className="text-center")


class BulkEvalPage(BasePage):
    title = "Evaluator"
    workflow = Workflow.BULK_EVAL
    slug_versions = ["bulk-eval", "eval"]

    explore_image = "https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/aad314f0-9a97-11ee-8318-02420a0001c7/W.I.9.png.png"

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
Add a CSV, Excel or Google Sheet url with the columns:
1. **Input prompt** for your questions
2. **Golden Answer** for your ideal output (optional)

TIP: Only the left most Sheet of Excel/Google Sheet is used so add ~3 rows of common QnAs while testing and then add more later to save time and credits.
            """,
        )

        eval_prompts: list[EvalPrompt] | None = Field(
            None,
            title="Evaluation Prompts",
            description="""
Add an LLM judge for each spreadsheet row.

`{{ columns | tojson(indent=2) }}` = row context plus every workflow field grouped under blind candidates.
            """,
        )

        agg_functions: list[AggFunction] | None = Field(
            None,
            title="Aggregations",
            description="""
Aggregate using one or more operations. Uses [pandas](https://pandas.pydata.org/pandas-docs/stable/reference/groupby.html#dataframegroupby-computations-descriptive-stats).
            """,
        )

        lower_is_better: bool = Field(
            False,
            title="Lower values are better",
            description="For metrics where lower values are better (e.g. error rate, latency, cost); tables and bar charts color green for lower aggregates when on.",
        )

        selected_model: str = "gpt_4_turbo"

        array_columns: list[str] | None = Field(None)

    class RequestModel(LanguageModelSettings, RequestModelBase):
        pass

    class ResponseModel(BaseModel):
        output_documents: list[str]
        final_prompts: list[list[str]] | None = None
        evaluation_results: list[list[dict | None]] | None = None
        aggregations: list[list[AggFunctionResult]] | None = None

    def render_form_v2(self):
        files = bulk_documents_uploader(
            f"##### {field_title(self.RequestModel, 'documents')}",
            accept=SUPPORTED_SPREADSHEET_TYPES,
            help=field_desc(self.RequestModel, "documents"),
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

        def render_inputs(key: str, _del_key: str, d: EvalPrompt):
            d["name"] = gui.text_input(
                label="",
                label_visibility="collapsed",
                placeholder="Metric Name",
                key=key + ":name",
                value=d.get("name"),
            ).strip()
            d["prompt"] = gui.code_editor(
                label="",
                label_visibility="collapsed",
                placeholder="Prompt",
                key=key + ":prompt",
                value=d.get("prompt"),
                language="jinja",
                style=dict(maxHeight="500px"),
            ).strip()

        llm_models = AIModelSpec.objects.filter(
            llm_supports_json=True,
        ).order_for_frontend(
            selected_models=gui.session_state.get("selected_model"),
        )
        options = {model.name: model.display_html() for model in llm_models}
        gui.selectbox(
            "##### Language Model",
            options=options,
            key="selected_model",
            format_func=options.__getitem__,
        )

        gui.write(
            "##### " + field_title(self.RequestModel, "eval_prompts"),
            help=field_desc(self.RequestModel, "eval_prompts"),
        )
        gui.session_state.setdefault("eval_prompts", [{}])
        list_view_editor(
            key="eval_prompts",
            render_inputs=render_inputs,
        )
        gui.checkbox(
            "##### " + field_title(self.RequestModel, "lower_is_better"),
            key="lower_is_better",
            help=field_desc(self.RequestModel, "lower_is_better"),
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
        gui.write(
            "##### " + field_title(self.RequestModel, "agg_functions"),
            help=field_desc(self.RequestModel, "agg_functions"),
        )
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
            gui.html(
                '<span class="float-end">'
                '<i class="fa fa-file-csv"></i>'
                f' <a href="{file}" target="_blank">Download</a>'
                "</span><br>"
            )
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
        response.evaluation_results = []
        response.aggregations = []

        with ThreadPoolExecutor(max_workers=4) as pool:
            futs = submit(pool, request, response)
            yield from iterate(futs, request, response)

    def fields_to_save(self) -> [str]:
        return super().fields_to_save() + [NROWS_CACHE_KEY]

    def get_raw_price(self, state: dict) -> float:
        nprompts = len(state.get("eval_prompts") or {}) or 1
        nrows = (
            state.get(NROWS_CACHE_KEY) or get_nrows(state.get("documents") or []) or 1
        )
        return nprompts * nrows

    def render_steps(self):
        documents = gui.session_state.get("documents") or []
        final_prompts = gui.session_state.get("final_prompts") or []
        evaluation_results = gui.session_state.get("evaluation_results") or []
        for doc, prompts, results in zip_longest(
            documents, final_prompts, evaluation_results, fillvalue=[]
        ):
            if not prompts:
                continue
            gui.write(f"###### {doc}")
            for i, prompt in enumerate(prompts):
                gui.write(f"**Evaluation Row {i + 1}**")
                gui.text_area("", value=prompt, key=f"--final-prompt-{i}")
                evaluation_result = results[i] if i < len(results) else None
                if evaluation_result is None:
                    continue

                gui.write("**Evaluation Result**")
                gui.json(evaluation_result, expanded=False)


class TaskResult(typing.NamedTuple):
    evaluation_result: dict
    doc_ix: int
    prompt_idx: int
    current_rec: dict
    input_cols: set[str]
    out_df_recs: list[dict]
    ep: EvalPrompt
    evaluation_tool: CandidateEvaluationTool


def submit(
    pool: ThreadPoolExecutor,
    request: BulkEvalPage.RequestModel,
    response: BulkEvalPage.ResponseModel,
) -> list[Future[TaskResult]]:
    futs = []
    for ep in request.eval_prompts or []:
        validate_eval_prompt(ep)
    for doc_ix, doc in enumerate(request.documents):
        response.output_documents.append(doc)
        response.final_prompts.append([])
        response.evaluation_results.append([])
        response.aggregations.append([])
        df = read_df_any(doc)
        evaluation_tool = None
        for out_df_recs, current_rec, prompt_columns in iter_eval_groups(
            df, request.array_columns
        ):
            for request_eval_prompt in request.eval_prompts or []:
                ep = dict(request_eval_prompt)
                render_columns, candidate_spec = build_candidate_columns(
                    prompt_columns,
                    request_eval_prompt["name"],
                )
                ep["candidate_spec"] = candidate_spec
                if evaluation_tool is None:
                    evaluation_tool = CandidateEvaluationTool(
                        output_column_names=candidate_spec["output_columns"],
                        candidate_labels=list(
                            candidate_spec["workflow_title_by_candidate"]
                        ),
                    )

                prompt = render_prompt_vars(
                    request_eval_prompt.get("prompt") or "",
                    gui.session_state | {"columns": render_columns},
                )
                if not prompt.strip():
                    raise UserError("Please provide a prompt")

                prompt_idx = len(response.final_prompts[doc_ix])
                response.final_prompts[doc_ix].append(prompt)
                response.evaluation_results[doc_ix].append(None)
                futs.append(
                    pool.submit(
                        _run_language_model,
                        model=request.selected_model,
                        prompt=prompt,
                        result=TaskResult(
                            evaluation_result={},
                            doc_ix=doc_ix,
                            prompt_idx=prompt_idx,
                            current_rec=current_rec,
                            input_cols=set(current_rec.keys()),
                            out_df_recs=out_df_recs,
                            ep=ep,
                            evaluation_tool=evaluation_tool,
                        ),
                    ),
                )
    return futs


def validate_eval_prompt(ep: EvalPrompt):
    if not (ep.get("name") or "").strip():
        raise UserError("Each evaluation prompt needs a name.")
    if not (ep.get("prompt") or "").strip():
        raise UserError(f"Eval prompt {ep.get('name')!r} needs a prompt.")


def build_candidate_columns(
    prompt_columns: dict,
    eval_name: str,
) -> tuple[dict, CandidateEvalSpec]:
    shared_input_columns = {}
    grouped_output_columns: dict[str, dict[str, typing.Any]] = {}
    candidate_by_workflow_title: dict[str, str] = {}

    for source_column, value in prompt_columns.items():
        workflow_title, output_column = _parse_workflow_column_parts(source_column)
        if not workflow_title:
            shared_input_columns[source_column] = value
            continue

        candidate = candidate_by_workflow_title.get(workflow_title)
        if candidate is None:
            candidate = _candidate_name(len(candidate_by_workflow_title))
            candidate_by_workflow_title[workflow_title] = candidate
        output_column = output_column or "Output"
        grouped_output_columns.setdefault(output_column, {})
        if candidate in grouped_output_columns[output_column]:
            raise UserError(
                f"Eval prompt {eval_name!r}: workflow {workflow_title!r} has more "
                f"than one spreadsheet column for output {output_column!r}."
            )
        grouped_output_columns[output_column][candidate] = value

    if not grouped_output_columns:
        raise UserError(
            f"Eval prompt {eval_name!r}: no workflow columns found. "
            "Expected Bulk Runner headers like `(My Workflow) Output Text`."
        )

    collisions = shared_input_columns.keys() & grouped_output_columns.keys()
    if collisions:
        collision_names = ", ".join(repr(col) for col in sorted(collisions))
        raise UserError(
            f"Eval prompt {eval_name!r}: input and workflow output columns use the "
            f"same name: {collision_names}. Rename the Bulk Runner output column."
        )

    for output_column, values_by_candidate in grouped_output_columns.items():
        if len(values_by_candidate) != len(candidate_by_workflow_title):
            raise UserError(
                f"Eval prompt {eval_name!r}: output column {output_column!r} is not "
                "available for every workflow. Bulk Runner workflows must have the "
                "same output columns."
            )

    candidate_spec: CandidateEvalSpec = {
        "output_columns": list(grouped_output_columns),
        "workflow_title_by_candidate": {
            candidate: workflow_title
            for workflow_title, candidate in candidate_by_workflow_title.items()
        },
    }
    return shared_input_columns | grouped_output_columns, candidate_spec


def _parse_workflow_column_parts(col: str) -> tuple[str | None, str | None]:
    if match := re.fullmatch(r"\((.*\S.*)\)(?:\s+(.+))?", col.strip()):
        return match[1].strip(), match[2].strip() if match[2] else None
    return None, None


def _candidate_name(index: int) -> str:
    name = ""
    while True:
        index, remainder = divmod(index, 26)
        name = chr(ord("A") + remainder) + name
        if index == 0:
            return name
        index -= 1


def iter_eval_groups(df: "pd.DataFrame", array_columns: list[str] | None):
    array_columns = [col for col in array_columns or [] if col in df.columns]
    out_df_recs = []
    prev_group_ix = None
    prompt_columns = {}

    for ix, row in enumerate(df.to_dict(orient="records")):
        out_df_recs.append(row)
        if not array_columns:
            yield out_df_recs, row, row.copy()
        else:
            # start new group if any non-array columns are present
            start_new_group = any(
                str(row.get(col) or "").strip()
                for col in df.columns
                if col not in array_columns
            )

            if start_new_group:
                if prev_group_ix is not None:
                    yield out_df_recs, out_df_recs[prev_group_ix], prompt_columns
                prev_group_ix = ix
                prompt_columns = row.copy()
                for col in array_columns:
                    prompt_columns[col] = []

            for col in array_columns:
                val = row.get(col)
                prompt_columns[col].append(val)
    if prev_group_ix is not None:
        yield out_df_recs, out_df_recs[prev_group_ix], prompt_columns


def _run_language_model(model: str, prompt: str, result: TaskResult):
    entries = []
    for entries in run_language_model(
        model=model,
        prompt=prompt,
        tools=[result.evaluation_tool],
        tool_choice="required",
        stream=True,
    ):
        pass
    tool_calls = entries[0].get("tool_calls") if entries else None
    if not tool_calls:
        raise UserError("The evaluator did not submit an evaluation result.")
    function_call = tool_calls[0]["function"]
    if function_call["name"] != result.evaluation_tool.name:
        raise UserError("The evaluator returned an unexpected tool call.")
    evaluation_result = json.loads(function_call["arguments"])

    assert isinstance(evaluation_result, dict)
    result.evaluation_result.update(evaluation_result)
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
        response.evaluation_results[result.doc_ix][result.prompt_idx] = (
            result.evaluation_result
        )

        apply_eval_metrics(result.current_rec, result.ep, result.evaluation_result)

        out_df = pd.DataFrame.from_records(result.out_df_recs)
        f = upload_file_from_bytes(
            filename=f"evaluator-{i + 1}.csv",
            data=out_df.to_csv(index=False).encode(),
            content_type="text/csv",
        )
        response.output_documents[result.doc_ix] = f

        aggs = []
        prefix = result.ep["name"] + " - "
        metric_cols = [
            col
            for col in out_df.select_dtypes(include=["number"]).columns
            if col not in result.input_cols and col.startswith(prefix)
        ]
        for agg in request.agg_functions or []:
            if agg.get("column"):
                cols = [agg["column"]]
            else:
                cols = metric_cols
            for col in cols:
                if col in result.input_cols:
                    continue
                col_values = out_df[col].dropna()
                agg_value = col_values.agg(agg["function"])
                aggs.append(
                    {
                        "column": col,
                        "function": agg["function"],
                        "count": len(col_values),
                        "value": agg_value,
                        "lower_is_better": request.lower_is_better,
                        "eval_prompt_name": result.ep["name"],
                    }
                )
        response.aggregations[result.doc_ix] = aggs


def apply_eval_metrics(
    current_rec: dict, ep: EvalPrompt, evaluation_result: dict
) -> None:
    eval_name = ep["name"]
    candidate_spec = ep["candidate_spec"]
    output_columns = candidate_spec["output_columns"]
    workflow_title_by_candidate = candidate_spec["workflow_title_by_candidate"]
    scores = evaluation_result["scores"]
    if not scores:
        raise ValueError("scores must contain at least one output column")

    evaluation_columns = {}
    include_output_column = len(output_columns) > 1

    for score in scores:
        output_column = score["column"]
        candidate_scores = score["candidates"]
        score_by_candidate = {
            item["candidate"]: item["score"] for item in candidate_scores
        }
        if len(candidate_scores) != len(workflow_title_by_candidate) or set(
            score_by_candidate
        ) != set(workflow_title_by_candidate):
            raise ValueError(
                f"scores for {output_column!r} must contain each candidate exactly once"
            )

        for candidate, workflow_title in workflow_title_by_candidate.items():
            if include_output_column:
                output_col = f"{eval_name} - {output_column} - {workflow_title}"
            else:
                output_col = f"{eval_name} - {workflow_title}"
            evaluation_columns[output_col] = float(score_by_candidate[candidate])

    for summary in evaluation_result.get("summaries", []):
        column = summary["column"].strip()
        if not column:
            raise ValueError("summary column names cannot be blank")
        value = summary["value"]
        output_col = f"{eval_name} - {column}"
        if output_col in evaluation_columns:
            raise ValueError(f"duplicate evaluation column: {column!r}")
        evaluation_columns[output_col] = workflow_title_by_candidate.get(value, value)

    current_rec.update(evaluation_columns)


@gui.cache_in_session_state
def get_nrows(files: list[str]) -> int:
    try:
        dfs = map_parallel(read_df_any, files)
    except ValueError:
        return 0
    return sum((len(df) for df in dfs), 0)

import itertools
import typing
import uuid
from itertools import zip_longest

from pydantic import BaseModel, Field

import gooey_ui as st
from bots.models import Workflow
from daras_ai.image_input import upload_file_from_bytes
from daras_ai_v2.base import BasePage
from daras_ai_v2.doc_search_settings_widgets import document_uploader
from daras_ai_v2.field_render import field_title_desc
from daras_ai_v2.functional import map_parallel
from daras_ai_v2.language_model import (
    run_language_model,
    LargeLanguageModels,
    llm_price,
)
from daras_ai_v2.language_model_settings_widgets import language_model_settings
from daras_ai_v2.prompt_vars import render_prompt_vars
from recipes.BulkRunner import read_df_any
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


class LLMSettingsMixin(BaseModel):
    selected_model: typing.Literal[tuple(e.name for e in LargeLanguageModels)] | None
    avoid_repetition: bool | None
    num_outputs: int | None
    quality: float | None
    max_tokens: int | None
    sampling_temperature: float | None


class EvalPrompt(typing.TypedDict):
    name: str
    prompt: str


class AggFunction(typing.TypedDict):
    column: str
    function: typing.Literal[tuple(AggFunctionsList)]


class AggFunctionResult(typing.TypedDict):
    column: str
    function: typing.Literal[tuple(AggFunctionsList)]
    count: int
    value: float


def _render_results(results: list[AggFunctionResult]):
    import plotly.graph_objects as go
    from plotly.colors import sample_colorscale
    from plotly.subplots import make_subplots

    for k, g in itertools.groupby(results, key=lambda d: d["function"]):
        st.write("---\n##### " + k.capitalize())

        g = list(g)
        columns = [d["column"] for d in g]
        values = [round(d["value"], 2) for d in g]
        norm_values = [(v - min(values)) / (max(values) - min(values)) for v in values]
        colors = sample_colorscale("RdYlGn", norm_values, colortype="tuple")
        colors = [f"rgba{(r * 255, g * 255, b * 255, 0.5)}" for r, g, b in colors]

        fig = make_subplots(
            rows=2,
            shared_xaxes=True,
            specs=[[{"type": "table"}], [{"type": "bar"}]],
            vertical_spacing=0.03,
            row_heights=[0.3, 0.7],
        )
        counts = [d.get("count", 1) for d in g]
        fig.add_trace(
            go.Table(
                header=dict(values=["Metric", k.capitalize(), "Count"]),
                cells=dict(
                    values=[columns, values, counts],
                    fill_color=["aliceblue", colors, "aliceblue"],
                ),
            ),
            row=1,
            col=1,
        )
        fig.add_trace(
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
            row=2,
            col=1,
        )
        fig.update_layout(
            margin=dict(l=0, r=0, t=24, b=0),
            # autosize=True,
        )
        st.plotly_chart(fig)


class BulkEvalPage(BasePage):
    title = "Bulk Evaluator"
    workflow = Workflow.BULK_EVAL
    slug_versions = ["bulk-eval", "eval"]

    class RequestModel(LLMSettingsMixin, BaseModel):
        documents: list[str] = Field(
            title="Input Data Spreadsheet",
            description="""
Upload or link to a CSV or google sheet that contains your sample input data. 
For example, for Copilot, this would sample questions or for Art QR Code, would would be pairs of image descriptions and URLs. 
Remember to includes header names in your CSV too.
            """,
        )

        eval_prompts: list[EvalPrompt] = Field(
            title="Evaluation Prompts",
            description="""
Specify custom LLM prompts to calculate metrics that evaluate each row of the input data. The output should be a JSON object mapping the metric names to values.  
_The `columns` dictionary can be used to reference the spreadsheet columns._            
            """,
        )

        agg_functions: list[AggFunction] | None = Field(
            title="Aggregations",
            description="""
Aggregate using one or more operations over the specified columns. Uses [pandas](https://pandas.pydata.org/pandas-docs/stable/reference/groupby.html#dataframegroupby-computations-descriptive-stats).
            """,
        )

    class ResponseModel(BaseModel):
        output_documents: list[str]
        aggregations: list[list[AggFunctionResult]] | None

    def render_form_v2(self):
        files = document_uploader(
            f"##### {field_title_desc(self.RequestModel, 'documents')}",
            accept=(".csv", ".xlsx", ".xls", ".json", ".tsv", ".xml"),
        )
        st.session_state[NROWS_CACHE_KEY] = get_nrows(files)
        if not files:
            return

        st.write(
            """
##### Input Data Preview
Here's what you uploaded:          
            """
        )
        for file in files:
            st.data_table(file)
        st.write("---")

        def render_inputs(key: str, del_key: str, d: EvalPrompt):
            col1, col2 = st.columns([1, 8], responsive=False)
            with col1:
                st.button("❌️", key=del_key, type="tertiary")
            with col2:
                d["name"] = st.text_input(
                    label="",
                    label_visibility="collapsed",
                    placeholder="Metric Name",
                    key=key + ":name",
                    value=d.get("name"),
                ).strip()
                d["prompt"] = st.text_area(
                    label="",
                    label_visibility="collapsed",
                    placeholder="Prompt",
                    key=key + ":prompt",
                    value=d.get("prompt"),
                    height=500,
                ).strip()

        st.write("##### " + field_title_desc(self.RequestModel, "eval_prompts"))
        list_view_editor(
            add_btn_label="➕ Add a Prompt",
            key="eval_prompts",
            render_inputs=render_inputs,
        )

        def render_inputs(key: str, del_key: str, d: AggFunction):
            col1, col2, col3 = st.columns([1, 5, 3], responsive=False)
            with col1:
                st.button("❌️", key=del_key, type="tertiary")
            with col2:
                d["column"] = st.text_input(
                    "",
                    label_visibility="collapsed",
                    placeholder="Column Name",
                    key=key + ":column",
                    value=d.get("column"),
                ).strip()
            with col3:
                d["function"] = st.selectbox(
                    "",
                    label_visibility="collapsed",
                    key=key + ":func",
                    options=AggFunctionsList,
                    default_value=d.get("function"),
                )

        st.html("<br>")
        st.write("##### " + field_title_desc(self.RequestModel, "agg_functions"))
        list_view_editor(
            add_btn_label="➕ Add an Aggregation",
            key="agg_functions",
            render_inputs=render_inputs,
        )

    def render_settings(self):
        language_model_settings()

    def render_example(self, state: dict):
        render_documents(state)

    def render_output(self):
        files = st.session_state.get("output_documents", [])
        aggregations = st.session_state.get("aggregations", [])

        for file, results in zip_longest(files, aggregations):
            st.write(file)
            st.data_table(file)

            if not results:
                continue

            _render_results(results)

    def run_v2(
        self,
        request: "BulkEvalPage.RequestModel",
        response: "BulkEvalPage.ResponseModel",
    ) -> typing.Iterator[str | None]:
        import pandas as pd

        response.output_documents = []
        response.aggregations = []

        for doc_ix, doc in enumerate(request.documents):
            df = read_df_any(doc)
            in_recs = df.to_dict(orient="records")
            out_recs = []

            out_df = None
            f = upload_file_from_bytes(
                filename=f"bulk-eval-{doc_ix}-0.csv",
                data=df.to_csv(index=False).encode(),
                content_type="text/csv",
            )
            response.output_documents.append(f)
            response.aggregations.append([])

            for df_ix in range(len(in_recs)):
                rec_ix = len(out_recs)
                out_recs.append(in_recs[df_ix])

                for ep_ix, ep in enumerate(request.eval_prompts):
                    progress = round(
                        (doc_ix + df_ix + ep_ix)
                        / (len(request.documents) + len(df) + len(request.eval_prompts))
                        * 100
                    )
                    yield f"{progress}%"
                    prompt = render_prompt_vars(
                        ep["prompt"],
                        st.session_state | {"columns": out_recs[rec_ix]},
                    )
                    ret = run_language_model(
                        model=LargeLanguageModels.gpt_4_turbo.name,
                        prompt=prompt,
                        response_format_type="json_object",
                    )[0]
                    assert isinstance(ret, dict)
                    for metric_name, metric_value in ret.items():
                        col = f"{ep['name']} - {metric_name}"
                        out_recs[rec_ix][col] = metric_value

                out_df = pd.DataFrame.from_records(out_recs)
                f = upload_file_from_bytes(
                    filename=f"bulk-runner-{doc_ix}-{df_ix}.csv",
                    data=out_df.to_csv(index=False).encode(),
                    content_type="text/csv",
                )
                response.output_documents[doc_ix] = f

            if out_df is None:
                continue
            for agg_ix, agg in enumerate(request.agg_functions):
                col_values = out_df[agg["column"]].dropna()
                agg_value = col_values.agg(agg["function"])
                response.aggregations[doc_ix].append(
                    {
                        "column": agg["column"],
                        "function": agg["function"],
                        "count": len(col_values),
                        "value": agg_value,
                    }
                )

    def fields_to_save(self) -> [str]:
        return super().fields_to_save() + [NROWS_CACHE_KEY]

    def get_raw_price(self, state: dict) -> float:
        try:
            price = llm_price[LargeLanguageModels[state["selected_model"]]]
        except KeyError:
            price = 1
        nprompts = len(state.get("eval_prompts") or {}) or 1
        nrows = (
            state.get(NROWS_CACHE_KEY) or get_nrows(state.get("documents") or []) or 1
        )
        return price * nprompts * nrows


@st.cache_in_session_state
def get_nrows(files: list[str]) -> int:
    dfs = map_parallel(read_df_any, files)
    return sum((len(df) for df in dfs), 0)


def list_view_editor(
    *,
    add_btn_label: str,
    key: str,
    render_labels: typing.Callable = None,
    render_inputs: typing.Callable[[str, str, dict], None],
):
    old_lst = st.session_state.setdefault(key, [])
    add_key = f"--{key}:add"
    if st.session_state.get(add_key):
        old_lst.append({})
    label_placeholder = st.div()
    new_lst = []
    for d in old_lst:
        entry_key = d.setdefault("__key__", f"--{key}:{uuid.uuid1()}")
        del_key = entry_key + ":del"
        if st.session_state.pop(del_key, None):
            continue
        render_inputs(entry_key, del_key, d)
        new_lst.append(d)
    if new_lst and render_labels:
        with label_placeholder:
            render_labels()
    st.session_state[key] = new_lst
    st.button(add_btn_label, key=add_key)

import datetime
import typing
from collections import Counter
from functools import partial

import gooey_gui as gui

from app_users.models import AppUser
from bots.models import BotIntegration, DataSelection, GraphType, Message
from bots.models.bot_integration import (
    BotIntegrationAnalysisChart,
)
from daras_ai.image_input import truncate_text_words
from daras_ai_v2 import icons
from daras_ai_v2.bot_integration_widgets import (
    analysis_runs_list_view,
    save_analysis_runs_for_integration,
)
from daras_ai_v2.grid_layout_widget import grid_layout
from daras_ai_v2.workflow_url_input import del_button
from gooeysite.custom_filters import JSONBExtractPath, related_json_field_summary
from recipes.BulkRunner import list_view_editor

if typing.TYPE_CHECKING:
    import plotly.graph_objects as go


# Modern color palette with 27 distinct colors
COLOR_PALETTE = [
    "#FF6B6B", "#45B7D1", "#96CEB4", "#FFEEAD", "#D4A5A5", "#9B59B6", "#3498DB", "#E74C3C", "#2ECC71", "#F1C40F",
    "#E67E22", "#1ABC9C", "#9B59B6", "#34495E", "#E74C3C", "#3498DB", "#2ECC71", "#F1C40F", "#E67E22", "#1ABC9C",
    "#9B59B6", "#34495E", "#E74C3C", "#3498DB", "#2ECC71", "#F1C40F",
]  # fmt: skip


def render_analysis_section(
    user: AppUser,
    bi: BotIntegration,
    start_date: datetime.datetime,
    end_date: datetime.datetime,
    label: str = '<i class="fa-solid fa-head-side-brain"></i> Analysis Results',
    key: str = "analysis_graphs",
):
    try:
        results = fetch_analysis_results(bi, start_date, end_date)
    except Message.DoesNotExist:
        results = None
    with (
        gui.styled("& .accordion-header { font-weight: 400; font-size: 1.4rem; }"),
        gui.div(),
        gui.expander(label),
    ):
        input_analysis_runs = analysis_runs_list_view(user, bi)

        if results:
            selected_graphs = analysis_graphs_list_view(bi, results, key)
        else:
            gui.caption(
                "No analysis results found. Add an analysis workflow and wait for the results to appear here, or select a date range to view results from a specific time period."
            )

        with gui.div(className="d-flex justify-content-end gap-3"):
            if gui.session_state.get(key + ":save"):
                save_analysis_runs_for_integration(bi, input_analysis_runs)
                save_analysis_charts_for_integration(bi, selected_graphs)
                gui.success("Saved!")

            gui.button(f"{icons.save} Save", type="primary", key=key + ":save")

    if results:
        render_graphs(bi, results, selected_graphs)


@gui.cache_in_session_state
def fetch_analysis_results(
    bi: BotIntegration,
    start_date: datetime.datetime | None = None,
    end_date: datetime.datetime | None = None,
) -> dict[str, typing.Any]:
    msgs = Message.objects.filter(
        conversation__bot_integration=bi,
    ).exclude(
        analysis_result={},
    )
    if start_date:
        msgs = msgs.filter(created_at__gte=start_date)
    if end_date:
        msgs = msgs.filter(created_at__lte=end_date)
    results = related_json_field_summary(
        Message.objects,
        "analysis_result",
        qs=msgs,
        query_param="--",
        instance_id=bi.id,
        max_keys=20,
    )
    return results


def analysis_graphs_list_view(
    bi: BotIntegration,
    results: dict[str, typing.Any] | None,
    key: str,
) -> list[dict[str, typing.Any]]:
    with gui.div(className="d-flex align-items-center gap-3 mb-2"):
        gui.write(
            '##### <i class="fa-solid fa-chart-line"></i> Analysis Graphs',
            unsafe_allow_html=True,
            help="Your bot's analysis script results can be visualized below. Make sure your analysis prompts return a consistent JSON Schema for best results!",
        )
        if gui.button(
            f"{icons.add} Add",
            type="tertiary",
            className="p-1 mb-2",
            key=key + ":add-graph",
        ):
            list_items = gui.session_state.setdefault(key, [])
            list_items.append({})

    # Load existing charts from DB
    if key not in gui.session_state:
        gui.session_state[key] = bi.analysis_charts.values(
            "result_field", "graph_type", "data_selection"
        )
    # Allow editing in the UI
    selected_graphs = list_view_editor(
        key=key,
        render_inputs=partial(render_inputs, results),
    )

    return selected_graphs


def render_graphs(
    bi: BotIntegration,
    results: dict[str, typing.Any] | None,
    selected_graphs: list[dict[str, typing.Any]],
):
    with gui.div(className="pb-5 pt-3"):
        grid_layout(
            2,
            selected_graphs,
            partial(render_graph_data, bi=bi, results=results),
        )


def save_analysis_charts_for_integration(
    bi: BotIntegration, selected_graphs: list[dict]
):
    """
    Save analysis charts for the given BotIntegration and clean up removed charts.
    """
    BotIntegrationAnalysisChart.objects.filter(bot_integration=bi).delete()
    for d in selected_graphs:
        BotIntegrationAnalysisChart.objects.create(
            bot_integration=bi,
            result_field=d["result_field"],
            graph_type=d["graph_type"],
            data_selection=d["data_selection"],
        )


def render_inputs(
    results: dict[str, typing.Any], key: str, del_key: str, d: dict[str, typing.Any]
):
    ocol1, ocol2 = gui.columns([11, 1], responsive=False)
    with ocol1:
        col1, col2, col3 = gui.columns(3)
    with ocol2:
        ocol2.node.props["style"] = dict(marginTop="1.5rem")
        del_button(del_key)

    with col1:
        d["result_field"] = gui.selectbox(
            label="##### JSON Field",
            options=results.keys(),
            key=f"{key}_key",
            value=d.get("result_field"),
        )
    with col2:
        d["graph_type"] = gui.selectbox(
            label="###### Graph Type",
            options=[g.value for g in GraphType],
            format_func=lambda x: GraphType(x).label,
            key=f"{key}_type",
            value=d.get("graph_type"),
        )
    with col3:
        d["data_selection"] = gui.selectbox(
            label="###### Data Selection",
            options=[d.value for d in DataSelection],
            format_func=lambda x: DataSelection(x).label,
            key=f"{key}_data_selection",
            value=d.get("data_selection"),
        )


def _autorefresh_script():
    if not gui.session_state.get("autorefresh"):
        return
    gui.session_state.pop("__cache__", None)
    gui.js(
        # language=JavaScript
        """
        setTimeout(() => {
            gui.rerun();
        }, 10000);
        """
    )


def render_graph_data(
    graph_data: dict[str, typing.Any],
    *,
    bi: BotIntegration,
    results: dict[str, typing.Any],
):
    key = graph_data["result_field"]
    with gui.center():
        gui.write(f"##### {key}")

    if graph_data["data_selection"] == DataSelection.last.value:
        latest_msg = (
            Message.objects.filter(conversation__bot_integration=bi)
            .annotate(val=JSONBExtractPath("analysis_result", key.split("__")))
            .exclude(val__isnull=True)
            .latest()
        )
        if not latest_msg:
            gui.write("No analysis results found")
            return
        values = [[latest_msg.analysis_result.get(key), 1]]
    elif graph_data["data_selection"] == DataSelection.convo_last.value:
        values_list = (
            Message.objects.filter(conversation__bot_integration=bi)
            .annotate(val=JSONBExtractPath("analysis_result", key.split("__")))
            .exclude(val__isnull=True)
            .order_by("conversation_id", "-created_at")
            .distinct("conversation_id")
            .values_list("val", flat=True)
        )
        counts = Counter(values_list)
        values = [[value, counts[value]] for value in counts]
    else:
        values = results[key]

    match graph_data["graph_type"]:
        case GraphType.display_values.value:
            for val in values:
                if not val:
                    continue
                gui.write(val[0])
        case GraphType.table_count.value:
            render_table_count(values)
        case GraphType.bar_count.value:
            render_bar_chart(values)
        case GraphType.pie_count.value:
            render_pie_chart(values)
        case GraphType.radar_count.value:
            render_radar_plot(values)


def render_table_count(values: list[list[typing.Any]]):
    if not values:
        gui.write("No analysis results found")
        return
    gui.div(className="p-1")
    total = sum(result[1] for result in values)
    gui.data_table(
        [["Value", "Count"], ["Total", total]]
        + [result[:2] for result in values if result[0]],
    )


def render_bar_chart(values: list[list[typing.Any]]):
    import plotly.graph_objects as go

    labels = [result[0] for result in values]
    short_labels = [truncate_label(label) for label in labels]
    y_vals = [result[1] for result in values]
    fig = make_figure(
        go.Bar(
            x=short_labels,
            y=y_vals,
            marker_color=COLOR_PALETTE,
            customdata=labels,
            hovertemplate="<b>%{customdata}</b><br>Count: %{y}<extra></extra>",
        )
    )
    fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=70),
        xaxis=dict(tickangle=-35),
    )
    gui.plotly_chart(fig, config={"displayModeBar": False, "displaylogo": False})


def render_pie_chart(values: list[list[typing.Any]]):
    import plotly.graph_objects as go

    labels = [result[0] for result in values]
    short_labels = [truncate_label(label) for label in labels]
    vals = [result[1] for result in values]
    pull = [0.05] + [0] * (len(vals) - 1)

    fig = make_figure(
        go.Pie(
            marker=dict(colors=COLOR_PALETTE),
            labels=short_labels,
            values=vals,
            textinfo="percent+label",
            textposition="inside",
            insidetextorientation="auto",
            pull=pull,
            showlegend=False,
            customdata=labels,
            hovertemplate="<b>%{customdata}</b><br>Count: %{value}<br>Percent: %{percent}<extra></extra>",
        )
    )
    fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
    )
    gui.plotly_chart(fig, config={"displayModeBar": False, "displaylogo": False})


def render_radar_plot(values: list[list[typing.Any]]):
    import plotly.graph_objects as go

    r = [result[1] for result in values]
    theta_full = [result[0] for result in values]
    theta = [truncate_label(label) for label in theta_full]
    if r and theta:
        r.append(r[0])
        theta.append(theta[0])
        theta_full.append(theta_full[0])
    # uniform fill/line base color
    fill_color = "#4ECDC4"

    fig = make_figure(
        go.Scatterpolar(
            r=r,
            theta=theta,
            fill="toself",
            fillcolor=fill_color,
            line=dict(color=fill_color),
            marker=dict(color=COLOR_PALETTE, size=8),
            customdata=theta_full,
            hovertemplate="<b>%{customdata}</b><br>Count: %{r}<extra></extra>",
        )
    )
    fig.update_layout(
        margin=dict(l=70, r=70, t=70, b=70),
    )
    gui.plotly_chart(fig)


def make_figure(*data: typing.Any) -> "go.Figure":
    import plotly.graph_objects as go

    fig = go.Figure(data=data)
    fig.update_layout(
        template="plotly_white",
        font=dict(size=12, family="basiercircle,sans-serif"),
        polar=dict(
            radialaxis=dict(angle=90, tickangle=90),
            angularaxis=dict(rotation=25),
        ),
        dragmode="pan",
        autosize=True,
        hovermode="x unified",
    )
    fig.update_xaxes(
        spikemode="across",
        spikedash="solid",
        spikecolor="rgba(126, 87, 194, 0.25)",  # soft purple, semi-transparent
        spikethickness=1,
    )
    return fig


def truncate_label(text: str) -> str:
    return truncate_text_words(text, 12, sep="…")

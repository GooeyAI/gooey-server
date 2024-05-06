import json
from collections import Counter

from django.db.models import IntegerChoices, Count

import gooey_ui as st
from bots.models import BotIntegration, Message
from daras_ai_v2.workflow_url_input import del_button
from gooey_ui import QueryParamsRedirectException
from gooeysite.custom_filters import related_json_field_summary
from recipes.BulkRunner import list_view_editor

MAX_LIMIT = 100


class GraphType(IntegerChoices):
    display_values = 1, "Display as Text"
    table_count = 2, "Table of Counts"
    bar_count = 3, "Bar Chart of Counts"
    pie_count = 4, "Pie Chart of Counts"
    radar_count = 5, "Radar Plot of Counts"


class DataSelection(IntegerChoices):
    all = 1, "All Data"
    last = 2, "Last Analysis"
    convo_last = 3, "Last Analysis per Conversation"


def render_analysis_results_page(bi: BotIntegration, old_graphs: str = None):
    st.div(className="p-2")
    if st.checkbox("🔄 Refresh every 10s"):
        st.session_state.pop("__cache__", None)
        st.js(
            # language=JavaScript
            """
            setTimeout(() => {
                gooeyRefresh();
            }, 10000);
            """
        )

    results = fetch_analysis_results(bi)
    if not results:
        st.write("No analysis results found")
        return

    def render_inputs(key: str, del_key: str, d: dict):
        col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
        with col1:
            d["key"] = st.selectbox(
                label="###### Key",
                options=results.keys(),
                key=f"{key}_key",
                value=d.get("key"),
            )
        with col2:
            d["graph_type"] = st.selectbox(
                label="###### Graph Type",
                options=[g.value for g in GraphType],
                format_func=lambda x: GraphType(x).label,
                key=f"{key}_type",
                value=d.get("graph_type"),
            )
        with col3:
            d["data_selection"] = st.selectbox(
                label="###### Data Selection",
                options=[d.value for d in DataSelection],
                format_func=lambda x: DataSelection(x).label,
                key=f"{key}_data_selection",
                value=d.get("data_selection"),
            )
        with col4:
            col4.node.props["style"] = dict(paddingTop="1.5rem")
            del_button(del_key)

    if old_graphs and "selected_graphs" not in st.session_state:
        st.session_state["selected_graphs"] = json.loads(old_graphs)

    placeholder = st.div(className="py-5")

    with st.expander("✏️ Edit"):
        graphs = list_view_editor(
            add_btn_label="➕ Add a Graph",
            key="selected_graphs",
            render_inputs=render_inputs,
        )

    new_graphs = (
        json.dumps(
            [
                dict(
                    key=d["key"],
                    graph_type=d["graph_type"],
                    data_selection=d["data_selection"],
                )
                for d in graphs
            ]
        )
        if graphs
        else None
    )
    if new_graphs != old_graphs:
        raise QueryParamsRedirectException(dict(graphs=new_graphs))

    with placeholder:
        for graph_data in graphs:
            render_graph_data(bi, results, graph_data)


@st.cache_in_session_state
def fetch_analysis_results(bi: BotIntegration) -> dict:
    msgs = Message.objects.filter(
        conversation__bot_integration=bi,
    ).exclude(
        analysis_result={},
    )
    results = related_json_field_summary(
        Message.objects,
        "analysis_result",
        qs=msgs,
        query_param="--",
        instance_id=bi.id,
        limit=MAX_LIMIT,
    )
    return results


def render_graph_data(bi, results, graph_data):
    key = graph_data["key"]
    st.write(f"##### {key}")
    obj_key = f"analysis_result__{key}"

    if graph_data["data_selection"] == DataSelection.last.value:
        latest_msg = (
            Message.objects.filter(conversation__bot_integration=bi)
            .exclude(**{obj_key: None})
            .latest()
        )
        if not latest_msg:
            st.write("No analysis results found")
            return
        values = [[latest_msg.analysis_result.get(key), 1]]
    elif graph_data["data_selection"] == DataSelection.convo_last.value:
        values_list = (
            Message.objects.filter(conversation__bot_integration=bi)
            .exclude(**{obj_key: None})
            .exclude(**{f"analysis_result__{key}": None})
            .order_by("conversation_id", "-created_at")
            .distinct("conversation_id")
            .values_list(obj_key, flat=True)
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
                st.write(val[0])
        case GraphType.table_count.value:
            render_table_count(values)
        case GraphType.bar_count.value:
            render_bar_chart(values)
        case GraphType.pie_count.value:
            render_pie_chart(values)
        case GraphType.radar_count.value:
            render_radar_plot(values)


def render_table_count(values):
    st.div(className="p-1")
    st.data_table(
        [["Value", "Count"]] + [[result[0], result[1]] for result in values],
    )


def render_bar_chart(values):
    import plotly.graph_objects as go

    render_data_in_plotly(
        go.Bar(
            x=[result[0] for result in values],
            y=[result[1] for result in values],
        ),
    )


def render_pie_chart(values):
    import plotly.graph_objects as go

    render_data_in_plotly(
        go.Pie(
            labels=[result[0] for result in values],
            values=[result[1] for result in values],
        ),
    )


def render_radar_plot(values):
    import plotly.graph_objects as go

    render_data_in_plotly(
        go.Scatterpolar(
            r=[result[1] for result in values],
            theta=[result[0] for result in values],
            fill="toself",
        ),
    )


def render_data_in_plotly(*data):
    import plotly.graph_objects as go

    fig = go.Figure(
        data=data,
        layout=go.Layout(
            template="plotly_white",
            font=dict(size=16),
        ),
    )
    st.plotly_chart(fig)

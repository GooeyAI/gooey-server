from gooeysite import wsgi

assert wsgi

import datetime

import pandas as pd
import plotly.express as px
import pytz
import streamlit as st

from bots.models import SavedRun
from daras_ai.text_format import format_timedelta
from daras_ai_v2.builder_analytics import (
    MAX_ANALYZED_RUNS,
    Outcome,
    build_error_stats,
    build_funnel,
    build_run_url,
    build_tool_stats,
    get_builder_prompt_rows,
    get_live_activity,
    get_user_labels,
    get_workspace_labels,
    workflow_label,
)
from daras_ai_v2.dashboard_filters import get_filtered_app_users
from widgets.plotly_theme import (
    COLOR_PALETTE,
    apply_consistent_styling,
    defaultPlotlyConfig,
)

st.set_page_config(layout="wide", page_title="Builder Analytics")

WINDOW_CHOICES = {
    "Last 15 minutes": datetime.timedelta(minutes=15),
    "Last hour": datetime.timedelta(hours=1),
    "Last 6 hours": datetime.timedelta(hours=6),
    "Last 24 hours": datetime.timedelta(days=1),
    "Last 7 days": datetime.timedelta(days=7),
    "Last 30 days": datetime.timedelta(days=30),
}
REFRESH_CHOICES = {"Off": None, "10s": 10, "30s": 30, "60s": 60}

# a live feed is only readable if it fits on a screen; the aggregate tabs read
# from the much larger MAX_ANALYZED_RUNS window instead
LIVE_FEED_LIMIT = 200


def main():
    st.title("🛠 Gooey Builder Analytics")
    st.caption(
        "Live user interactions, the builder prompts people are writing, "
        "and what they actually got out of them."
    )

    filters = render_sidebar()

    live_tab, prompts_tab, outcomes_tab = st.tabs(
        ["⚡ Live Activity", "💬 Builder Prompts", "🎯 Outcomes"]
    )
    with live_tab:
        render_live_activity(filters)
    with prompts_tab:
        render_builder_prompts(filters)
    with outcomes_tab:
        render_outcomes(filters)


def render_sidebar() -> dict:
    with st.sidebar:
        st.header("Filters")

        timezone = pytz.timezone(
            st.selectbox(
                "Timezone",
                pytz.common_timezones,
                index=pytz.common_timezones.index("Asia/Kolkata"),
            )
        )
        window_label = st.selectbox(
            "Time window", list(WINDOW_CHOICES), index=3, key="window"
        )
        refresh_label = st.selectbox(
            "Auto-refresh", list(REFRESH_CHOICES), index=2, key="refresh"
        )

        st.divider()
        exclude_anon = st.checkbox("Exclude Anonymous", value=True)
        exclude_team = st.checkbox("Exclude Team", value=False)
        exclude_disabled = st.checkbox("Exclude Banned", value=True)

        st.divider()
        surface_labels = st.multiselect(
            "Surfaces (Live Activity)",
            options=[s.label for s in SavedRun.Surface],
            default=[],
            help="Leave empty to show every surface.",
        )
        mask_prompts = st.checkbox(
            "Mask prompt text",
            value=False,
            help="Hide user-written prompts so this dashboard is safe to screenshare.",
        )

    now = datetime.datetime.now(tz=datetime.timezone.utc)
    window = WINDOW_CHOICES[window_label]
    return dict(
        timezone=timezone,
        start=now - window,
        end=now,
        window=window,
        window_label=window_label,
        refresh_every=REFRESH_CHOICES[refresh_label],
        surfaces=[s.value for s in SavedRun.Surface if s.label in surface_labels],
        mask_prompts=mask_prompts,
        exclude_anon=exclude_anon,
        exclude_team=exclude_team,
        exclude_disabled=exclude_disabled,
    )


def get_uid_filter(*, exclude_anon: bool, exclude_team: bool, exclude_disabled: bool):
    if not (exclude_anon or exclude_team or exclude_disabled):
        return None
    return get_filtered_app_users(
        exclude_anon=exclude_anon,
        exclude_team=exclude_team,
        exclude_disabled=exclude_disabled,
    ).values("uid")


## Live Activity ##############################################################


def render_live_activity(filters: dict):
    st.subheader("Live Activity")
    st.caption(
        f"Most recent {LIVE_FEED_LIMIT} runs · {filters['window_label'].lower()}"
    )
    render_activity_feed(filters)


def render_activity_feed(filters: dict):
    """Re-runs on its own timer without touching the rest of the page."""

    @st.fragment(run_every=filters["refresh_every"])
    def _feed():
        st.caption(f"Updated {datetime.datetime.now(filters['timezone']):%H:%M:%S}")
        rows = get_live_activity(
            # the feed always shows *now*, not the timestamp captured on the
            # rerun that first drew this fragment
            start=datetime.datetime.now(tz=datetime.timezone.utc) - filters["window"],
            end=datetime.datetime.now(tz=datetime.timezone.utc),
            surfaces=filters["surfaces"],
            uids=get_uid_filter(
                exclude_anon=filters["exclude_anon"],
                exclude_team=filters["exclude_team"],
                exclude_disabled=filters["exclude_disabled"],
            ),
            limit=LIVE_FEED_LIMIT,
        )
        if not rows:
            st.info("No runs in this window.")
            return

        user_labels = get_user_labels(row["uid"] for row in rows)
        workspace_labels = get_workspace_labels(row["workspace_id"] for row in rows)

        render_live_metrics(rows)
        df = pd.DataFrame.from_records(
            [
                {
                    "Time": row["created_at"].astimezone(filters["timezone"]),
                    "Status": row["status"],
                    "User": user_labels.get(row["uid"], row["uid"] or "—"),
                    "Workspace": workspace_labels.get(row["workspace_id"], "—"),
                    "Surface": SavedRun.Surface(row["surface"]).label
                    if row["surface"] is not None
                    else "—",
                    "Workflow": workflow_label(row["workflow"]),
                    "Prompt": mask(row["input_prompt"], filters),
                    "Run time": format_timedelta(row["run_time"])
                    if row["run_time"]
                    else "",
                    "Credits": row["price"],
                    "Error": row["error_type"] or "",
                    "URL": row["url"],
                }
                for row in rows
            ]
        )
        st.dataframe(
            df,
            hide_index=True,
            use_container_width=True,
            column_config={"URL": st.column_config.LinkColumn("URL", display_text="↗")},
        )

    _feed()


def render_live_metrics(rows: list[dict]):
    errors = sum(1 for row in rows if row["error_msg"])
    running = sum(1 for row in rows if row["run_status"] and not row["error_msg"])
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Runs", len(rows))
    col2.metric("Running now", running)
    col3.metric("Errors", errors)
    col4.metric("Unique users", len({row["uid"] for row in rows if row["uid"]}))


## Builder Prompts ############################################################


def render_builder_prompts(filters: dict):
    st.subheader("Builder Prompts")
    rows, truncated = load_builder_rows(filters)
    if not rows:
        st.info("No builder prompts in this window.")
        return
    warn_if_truncated(truncated)

    user_labels = get_user_labels(row["uid"] for row in rows)
    workspace_labels = get_workspace_labels(row["workspace_id"] for row in rows)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Prompts", len(rows))
    col2.metric("Unique users", len({row["uid"] for row in rows if row["uid"]}))
    col3.metric("Conversations", len({row["message_thread_id"] for row in rows}))
    col4.metric(
        "Reached deploy",
        sum(1 for row in rows if row["outcome"] == Outcome.deployed),
    )

    df = pd.DataFrame.from_records(
        [
            {
                "Time": row["created_at"].astimezone(filters["timezone"]),
                "Outcome": row["outcome"],
                "User": user_labels.get(row["uid"], row["uid"] or "—"),
                "Workspace": workspace_labels.get(row["workspace_id"], "—"),
                "Prompt": mask(row["input_prompt"], filters),
                "Conversation": mask(row["thread_title"], filters),
                "Tools": " ".join(str(c) for c in row["transcript"].tool_calls),
                "Reply": mask(row["transcript"].assistant_text, filters),
                "Run time": format_timedelta(row["run_time"])
                if row["run_time"]
                else "",
                "Credits": row["price"],
                "Error": row["error_type"] or "",
                "Builder run": build_run_url(
                    workflow=row["workflow"], run_id=row["run_id"], uid=row["uid"]
                ),
                "Workflow": row["child_url"],
            }
            for row in rows
        ]
    )
    st.dataframe(
        df,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Builder run": st.column_config.LinkColumn("Builder run", display_text="↗"),
            "Workflow": st.column_config.LinkColumn("Workflow", display_text="↗"),
        },
    )

    render_conversation_rollup(rows, filters, user_labels)
    render_prompt_drilldown(rows, filters, user_labels)


def render_conversation_rollup(rows: list[dict], filters: dict, user_labels: dict):
    """Multi-turn view - how many prompts it takes to get to an outcome."""
    st.markdown("#### Conversations")
    threads: dict = {}
    for row in rows:
        # prompts with no thread are standalone; key them by their own id so
        # they still show up as one-turn conversations
        key = row["message_thread_id"] or f"run:{row['id']}"
        thread = threads.setdefault(
            key,
            dict(
                title=row["thread_title"],
                user=user_labels.get(row["uid"], row["uid"] or "—"),
                turns=0,
                first_prompt=row["input_prompt"],
                started_at=row["created_at"],
                last_at=row["created_at"],
                outcomes=[],
            ),
        )
        thread["turns"] += 1
        # rows arrive newest first
        thread["first_prompt"] = row["input_prompt"] or thread["first_prompt"]
        thread["started_at"] = min(thread["started_at"], row["created_at"])
        thread["last_at"] = max(thread["last_at"], row["created_at"])
        thread["outcomes"].append(row["outcome"])

    df = pd.DataFrame.from_records(
        [
            {
                "Started": thread["started_at"].astimezone(filters["timezone"]),
                "User": thread["user"],
                "Turns": thread["turns"],
                "Best outcome": best_outcome(thread["outcomes"]),
                "Title": mask(thread["title"], filters),
                "First prompt": mask(thread["first_prompt"], filters),
                "Duration": format_timedelta(thread["last_at"] - thread["started_at"]),
            }
            for thread in threads.values()
        ]
    ).sort_values("Started", ascending=False)
    st.dataframe(df, hide_index=True, use_container_width=True)


def render_prompt_drilldown(rows: list[dict], filters: dict, user_labels: dict):
    st.markdown("#### Inspect a prompt")
    options = {
        f"{row['created_at'].astimezone(filters['timezone']):%H:%M:%S} · "
        f"{user_labels.get(row['uid'], row['uid'] or '—')} · "
        f"{row['outcome']} · {truncate(row['input_prompt'], 60)}": row
        for row in rows[:100]
    }
    label = st.selectbox("Prompt", list(options), index=0)
    if not label:
        return
    row = options[label]

    st.markdown("**Prompt**")
    st.code(mask(row["input_prompt"], filters) or "—", language=None)
    st.markdown("**Reply**")
    st.code(
        mask(row["transcript"].assistant_text, filters) or "—",
        language=None,
    )
    if row["error_msg"]:
        st.error(f"{row['error_type']}: {row['error_msg']}")

    if not row["transcript"].tool_calls:
        st.caption("No tool calls.")
        return
    st.markdown("**Tool calls**")
    for call in row["transcript"].tool_calls:
        with st.expander(f"{call.status} {call.name}"):
            st.json(call.arguments)
            if call.error:
                st.error(call.error)
            if call.result_url:
                st.link_button("Open result", call.result_url)


## Outcomes ###################################################################


def render_outcomes(filters: dict):
    st.subheader("Outcomes")
    rows, truncated = load_builder_rows(filters)
    if not rows:
        st.info("No builder prompts in this window.")
        return
    warn_if_truncated(truncated)

    col1, col2 = st.columns(2)
    with col1:
        render_funnel(rows)
    with col2:
        render_outcome_mix(rows)

    st.markdown("#### Tool success rates")
    tool_stats = build_tool_stats(rows)
    if tool_stats:
        st.dataframe(
            pd.DataFrame.from_records(tool_stats).rename(
                columns={
                    "tool": "Tool",
                    "calls": "Calls",
                    "ok": "Succeeded",
                    "failed": "Failed",
                    "unknown": "No result",
                    "success_rate": "Success %",
                }
            ),
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.caption("No tool calls in this window.")

    st.markdown("#### Top failure modes")
    error_stats = build_error_stats(rows)
    if error_stats:
        st.dataframe(
            pd.DataFrame.from_records(error_stats[:50]).rename(
                columns={"source": "Source", "error": "Error", "count": "Count"}
            ),
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.caption("No errors in this window. 🎉")

    render_volume_over_time(rows, filters)


def render_funnel(rows: list[dict]):
    st.markdown("#### Funnel")
    funnel = build_funnel(rows)
    fig = px.funnel(
        pd.DataFrame.from_records(funnel),
        x="count",
        y="step",
        color_discrete_sequence=COLOR_PALETTE,
    )
    fig.update_layout(yaxis_title=None, xaxis_title=None, showlegend=False)
    st.plotly_chart(
        apply_consistent_styling(fig),
        use_container_width=True,
        config=defaultPlotlyConfig,
    )
    st.dataframe(
        pd.DataFrame.from_records(funnel).rename(
            columns={
                "step": "Step",
                "count": "Count",
                "pct_of_prompts": "% of prompts",
            }
        ),
        hide_index=True,
        use_container_width=True,
    )


def render_outcome_mix(rows: list[dict]):
    st.markdown("#### Outcome mix")
    counts = {}
    for row in rows:
        counts[row["outcome"]] = counts.get(row["outcome"], 0) + 1
    df = pd.DataFrame(
        [
            dict(outcome=outcome, count=counts[outcome])
            for outcome in Outcome.funnel_order
            if outcome in counts
        ]
    )
    fig = px.pie(
        df, names="outcome", values="count", color_discrete_sequence=COLOR_PALETTE
    )
    fig.update_traces(textposition="inside", textinfo="percent+label")
    fig.update_layout(showlegend=False)
    st.plotly_chart(
        apply_consistent_styling(fig),
        use_container_width=True,
        config=defaultPlotlyConfig,
    )


def render_volume_over_time(rows: list[dict], filters: dict):
    st.markdown("#### Prompts over time")
    df = pd.DataFrame.from_records(
        [
            {
                "Time": row["created_at"].astimezone(filters["timezone"]),
                "Outcome": row["outcome"],
            }
            for row in rows
        ]
    )
    # a 30 day window in 1 minute buckets is unreadable; scale the bucket to the window
    span = filters["end"] - filters["start"]
    freq = (
        "1min"
        if span <= datetime.timedelta(hours=6)
        else ("1h" if span <= datetime.timedelta(days=2) else "1D")
    )
    grouped = (
        df.groupby([pd.Grouper(key="Time", freq=freq), "Outcome"])
        .size()
        .reset_index(name="Prompts")
    )
    fig = px.bar(
        grouped,
        x="Time",
        y="Prompts",
        color="Outcome",
        color_discrete_sequence=COLOR_PALETTE,
    )
    fig.update_layout(xaxis_title=None, barmode="stack")
    st.plotly_chart(
        apply_consistent_styling(fig),
        use_container_width=True,
        config=defaultPlotlyConfig,
    )


## helpers ####################################################################


@st.cache_data(ttl=60, show_spinner="Loading builder prompts...")
def _load_builder_rows_cached(
    start: datetime.datetime,
    end: datetime.datetime,
    exclude_anon: bool,
    exclude_team: bool,
    exclude_disabled: bool,
) -> tuple[list[dict], bool]:
    # the uid filter stays a subquery - resolving it here would drag the whole
    # user table into an IN clause (and into the cache key)
    return get_builder_prompt_rows(
        start=start,
        end=end,
        uids=get_uid_filter(
            exclude_anon=exclude_anon,
            exclude_team=exclude_team,
            exclude_disabled=exclude_disabled,
        ),
    )


def load_builder_rows(filters: dict) -> tuple[list[dict], bool]:
    """Aggregates are expensive to compute, so they lag the live feed by <=60s."""
    return _load_builder_rows_cached(
        # start/end move on every rerun, which would make the cache useless;
        # bucketing to the minute lets reruns inside the same minute share an entry
        filters["start"].replace(second=0, microsecond=0),
        filters["end"].replace(second=0, microsecond=0),
        filters["exclude_anon"],
        filters["exclude_team"],
        filters["exclude_disabled"],
    )


def warn_if_truncated(truncated: bool):
    if truncated:
        st.warning(
            f"More than {MAX_ANALYZED_RUNS:,} prompts in this window - "
            f"showing the {MAX_ANALYZED_RUNS:,} most recent. "
            "Narrow the time window for exact numbers."
        )


def best_outcome(outcomes: list[str]) -> str:
    return max(outcomes, key=Outcome.funnel_order.index, default="")


def mask(text: str | None, filters: dict) -> str:
    text = text or ""
    if filters["mask_prompts"] and text:
        return f"[{len(text)} chars hidden]"
    return text


def truncate(text: str | None, maxlen: int) -> str:
    text = (text or "").strip().replace("\n", " ")
    if len(text) > maxlen:
        return text[: maxlen - 1] + "…"
    return text


main()

import datetime
import typing
from functools import partial

import gooey_gui as gui
import pandas as pd
import plotly.graph_objects as go
from django.db.models import (
    Avg,
    CharField,
    Count,
    Q,
    Sum,
)
from django.db.models.functions import (
    Concat,
    TruncDay,
    TruncMonth,
    TruncWeek,
)
from django.db.models.functions.datetime import TruncBase
import pytz

from bots.models import BotIntegration, Message
from bots.models.convo_msg import CHATML_ROLE_ASSISTANT, Feedback
from widgets.plotly_theme import (
    COLOR_PALETTE,
    apply_consistent_styling,
    defaultPlotlyConfig,
)


def render_copilot_stats_plots(
    bi: BotIntegration,
    tz: pytz.timezone,
    start_date: datetime.datetime,
    end_date: datetime.datetime,
    frequency: typing.Literal["Daily", "Weekly", "Monthly"],
):
    if start_date > end_date:
        start_date = end_date

    match frequency:
        case "Daily":
            trunc_fn = partial(TruncDay, tzinfo=tz)
            tdelta = datetime.timedelta(days=1)
            pd_freq = "D"
        case "Weekly":
            trunc_fn = partial(TruncWeek, tzinfo=tz)
            tdelta = datetime.timedelta(days=7)
            pd_freq = "W"
        case "Monthly":
            trunc_fn = partial(TruncMonth, tzinfo=tz)
            tdelta = datetime.timedelta(days=30)
            pd_freq = "M"

    fig = go.Figure()

    # Apply consistent styling from analysis_results.py
    fig = apply_consistent_styling(fig)

    fig.update_yaxes(tickformat="d")
    fig.update_layout(
        height=1200,
        margin=dict(l=0, r=0, t=20, b=70),
        grid=dict(rows=5, columns=1),
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.01,
            xanchor="center",
            x=0.5,
        ),
    )

    try:
        dt_index = plot_active_users(fig, bi, start_date, end_date, trunc_fn, pd_freq)
    except Message.DoesNotExist:
        gui.write("No data to show yet. Please select a different date range.")
        return

    fig.update_xaxes(
        type="date",
        dtick=calc_dtick(dt_index.iloc[0], dt_index.iloc[-1], tdelta),
        showticklabels=True,
        showgrid=False,
    )

    plot_messages_sent(fig, bi, start_date, end_date, trunc_fn, pd_freq)
    plot_average_runtime(fig, bi, start_date, end_date, trunc_fn, pd_freq)
    plot_total_price(fig, bi, start_date, end_date, trunc_fn, pd_freq)
    plot_retention(fig, bi, start_date, end_date, trunc_fn, pd_freq, dt_index)

    gui.plotly_chart(fig, config=defaultPlotlyConfig)


def plot_active_users(
    fig: go.Figure,
    bi: BotIntegration,
    start_date: datetime.datetime,
    end_date: datetime.datetime,
    trunc_fn: TruncBase,
    pd_freq: str,
):
    qs = (
        Message.objects.filter(
            conversation__bot_integration=bi,
            created_at__range=(start_date, end_date),
            role=CHATML_ROLE_ASSISTANT,
        )
        .annotate(dt=trunc_fn("created_at"))
        .values("dt")
    )

    qs_list = [
        qs.annotate(
            msg_count=Count("id"),
        ).values("dt", "msg_count"),
        qs.annotate(
            user_count=Count(
                Concat(*Message.convo_user_id_fields, output_field=CharField()),
                distinct=True,
            )
        ).values("dt", "user_count"),
    ]
    if not any(qs_list):
        raise Message.DoesNotExist("No data found")

    df = pd.concat(
        [pd.DataFrame.from_dict(v).set_index("dt") for v in qs_list if v],
        axis=1,
    )

    # resample to the correct frequency
    df = df.resample(pd_freq).sum().reset_index()
    # render the plot
    fig.add_trace(
        go.Scatter(
            x=df["dt"].tolist(),
            y=df["user_count"].tolist(),
            hovertemplate="Active Users: %{y}<extra></extra>",
            line_shape="spline",
            **get_line_marker(color_idx=1, gradient=True),
            xaxis="x",
            yaxis="y",
            name="Active Users",
        )
    )
    add_legend(fig, "Active Users", color_idx=1, row=1)
    fig.add_trace(
        go.Scatter(
            x=df["dt"].tolist(),
            y=(df["msg_count"] / df["user_count"]).fillna(0).tolist(),
            hovertemplate="Avg Messages per User: %{y:.0f}<extra></extra>",
            line_shape="spline",
            **get_line_marker(color_idx=2),
            xaxis="x",
            yaxis="y10",
            name="Avg Messages per User",
        )
    )
    fig.update_layout(
        yaxis10=dict(
            overlaying="y",
            side="right",
            showgrid=False,
        )
    )
    return pd.to_datetime(df.dt)


def plot_messages_sent(
    fig: go.Figure,
    bi: BotIntegration,
    start_date: datetime.datetime,
    end_date: datetime.datetime,
    trunc_fn: TruncBase,
    pd_freq: str,
):
    qs = (
        Message.objects.select_related("feedbacks")
        .filter(
            conversation__bot_integration=bi,
            created_at__range=(start_date, end_date),
            role=CHATML_ROLE_ASSISTANT,
        )
        .annotate(dt=trunc_fn("created_at"))
        .values("dt")
    )

    qs_list = [
        qs.annotate(
            count=Count("id"),
        ).values("dt", "count"),
        qs.annotate(
            pos_count=Count(
                "feedbacks__message",
                filter=Q(feedbacks__rating=Feedback.Rating.POSITIVE),
                distinct=True,
            ),
        ).values("dt", "pos_count"),
        qs.annotate(
            neg_count=Count(
                "feedbacks__message",
                filter=Q(feedbacks__rating=Feedback.Rating.NEGATIVE),
                distinct=True,
            ),
        ).values("dt", "neg_count"),
        qs.annotate(
            success_count=Count(
                "id",
                filter=Q(analysis_result__contains={"Answered": True})
                | Q(analysis_result__contains={"assistant": {"answer": "Found"}}),
            ),
        ).values("dt", "success_count"),
    ]
    if not any(qs_list):
        return

    df = pd.concat(
        [pd.DataFrame.from_dict(v).set_index("dt") for v in qs_list if v],
        axis=1,
    )

    # resample to the correct frequency
    df = df.resample(pd_freq).sum().reset_index()

    # render the plot
    fig.add_trace(
        go.Scatter(
            x=df["dt"].tolist(),
            y=(df["count"]).tolist(),
            hovertemplate="Messages: %{y}<extra></extra>",
            line_shape="spline",
            **get_line_marker(color_idx=6, gradient=True),
            xaxis="x",
            yaxis="y2",
            name="Messages",
        )
    )
    add_legend(fig, "Interactions", color_idx=6, row=2)

    if df["pos_count"].any():
        fig.add_trace(
            go.Scatter(
                x=df["dt"].tolist(),
                y=df["pos_count"].tolist(),
                customdata=(df["pos_count"] / df["count"]).fillna(0).tolist(),
                hovertemplate="Positive Feedback: %{y} (%{customdata:.0%})<extra></extra>",
                line_shape="spline",
                **get_line_marker(color_idx=2),
                xaxis="x",
                yaxis="y2",
                name="Positive Feedback",
            )
        )
    if df["success_count"].any():
        fig.add_trace(
            go.Scatter(
                x=df["dt"].tolist(),
                y=df["success_count"].tolist(),
                customdata=(df["success_count"] / df["count"]).fillna(0).tolist(),
                hovertemplate="Answered Successfully: %{y} (%{customdata:.0%})<extra></extra>",
                line_shape="spline",
                **get_line_marker(color_idx=11),
                xaxis="x",
                yaxis="y2",
                name="Answered Successfully",
            )
        )
    if df["neg_count"].any():
        fig.add_trace(
            go.Scatter(
                x=df["dt"].tolist(),
                y=df["neg_count"].tolist(),
                customdata=(df["neg_count"] / df["count"]).fillna(0).tolist(),
                hovertemplate="Negative Feedback: %{y} (%{customdata:.0%})<extra></extra>",
                line_shape="spline",
                **get_line_marker(color_idx=10),
                xaxis="x",
                yaxis="y2",
                name="Negative Feedback",
            )
        )


def plot_average_runtime(
    fig: go.Figure,
    bi: BotIntegration,
    start_date: datetime.datetime,
    end_date: datetime.datetime,
    trunc_fn: TruncBase,
    pd_freq: str,
):
    qs = (
        # get messages for the given bot integration and date range
        Message.objects.filter(
            conversation__bot_integration=bi,
            created_at__range=(start_date, end_date),
            saved_run__isnull=False,  # Only include messages with saved runs
        )
        # truncate the date to the correct frequency
        .annotate(dt=trunc_fn("created_at"))
        # get the average run time for each date
        .values("dt")
        .annotate(avg_run_time=Avg("saved_run__run_time"))
        # order by date
        .order_by("dt")
        .values("dt", "avg_run_time")
    )
    if not qs:
        return
    df = pd.DataFrame.from_dict(qs)
    # resample to the correct frequency and calculate mean
    df = df.set_index("dt").resample(pd_freq).mean().reset_index()

    # convert timedelta64[ns] to seconds, set nan to 0
    df["avg_run_time"] = df["avg_run_time"].dt.total_seconds().fillna(0)

    # render the plot
    fig.add_trace(
        go.Scatter(
            x=df["dt"].tolist(),
            y=df["avg_run_time"].tolist(),
            hovertemplate="Avg Run Time: %{y:.1f}s<extra></extra>",
            line_shape="spline",
            **get_line_marker(color_idx=4, gradient=True),
            xaxis="x",
            yaxis="y3",
            name="Avg Run Time",
        )
    )
    add_legend(fig, "Avg Run Time", color_idx=4, row=3)


def plot_total_price(
    fig: go.Figure,
    bi: BotIntegration,
    start_date: datetime.datetime,
    end_date: datetime.datetime,
    trunc_fn: TruncBase,
    pd_freq: str,
):
    qs = (
        # get messages for the given bot integration and date range
        Message.objects.filter(
            conversation__bot_integration=bi,
            created_at__range=(start_date, end_date),
            saved_run__isnull=False,  # Only include messages with saved runs
        )
        # truncate the date to the correct frequency
        .annotate(dt=trunc_fn("created_at"))
        # get the average run time for each date
        .values("dt")
        .annotate(total_price=Sum("saved_run__price"))
        # order by date
        .order_by("dt")
        .values("dt", "total_price")
    )
    if not qs:
        return
    df = pd.DataFrame.from_dict(qs)
    # resample to the correct frequency and calculate mean
    df = df.set_index("dt").resample(pd_freq).mean().reset_index()
    df["total_price"] = df["total_price"].fillna(0)

    # render the plot
    fig.add_trace(
        go.Scatter(
            x=df["dt"].tolist(),
            y=df["total_price"].tolist(),
            hovertemplate="Credits Used: %{y:.1f}<extra></extra>",
            line_shape="spline",
            **get_line_marker(color_idx=5, gradient=True),
            xaxis="x",
            yaxis="y4",
            name="Credits Used",
        )
    )
    add_legend(fig, "Credits Used", color_idx=5, row=4)


def plot_retention(
    fig: go.Figure,
    bi: BotIntegration,
    start_date: datetime.datetime,
    end_date: datetime.datetime,
    trunc_fn: TruncBase,
    pd_freq: str,
    dt_index: pd.Index,
):
    if dt_index.empty:
        return
    cohort = (start_date, dt_index.iloc[0] + datetime.timedelta(days=1))
    qs = (
        Message.objects.filter(
            conversation__bot_integration=bi,
            created_at__range=(start_date, end_date),
        )
        .annotate(dt=trunc_fn("created_at"))
        .values("dt")
        .annotate(
            counts=Count(
                Concat(*Message.convo_user_id_fields, output_field=CharField()),
                filter=Q(
                    conversation__bot_integration=bi,
                    conversation__messages__created_at__range=cohort,
                ),
                distinct=True,
            ),
        )
        .values("dt", "counts")
    )

    df = pd.DataFrame.from_dict(qs)
    df = df.set_index("dt").resample(pd_freq).sum().reset_index()

    fig.add_trace(
        go.Scatter(
            x=df["dt"].tolist(),
            y=(df["counts"] / df["counts"].iloc[0] * 100).fillna(0).tolist(),
            customdata=df["counts"].tolist(),
            hovertemplate="Retention: %{y:.0f}% (%{customdata:.0f} Users)<extra></extra>",
            line_shape="spline",
            **get_line_marker(color_idx=9, gradient=True),
            xaxis="x",
            yaxis="y5",
            name="Retention",
        )
    )
    add_legend(fig, "Retention", color_idx=9, row=5)


def get_line_marker(*, color_idx: int, gradient: bool = False):
    ret = dict(
        line=dict(color=COLOR_PALETTE[color_idx]),
        marker=dict(
            color="white", size=6, line=dict(color=COLOR_PALETTE[color_idx], width=2)
        ),
    )
    if gradient:
        ret["fill"] = "tozeroy"
        ret["fillgradient"] = dict(
            type="vertical",
            colorscale=[
                (0.0, "white"),
                (0.1, "white"),
                (1.0, hex_to_rgba(COLOR_PALETTE[color_idx], 0.2)),
            ],
        )
    return ret


def add_legend(fig: go.Figure, text: str, color_idx: int, row: int):
    nrows = fig.layout.grid.rows
    y = 1 - (row - 1) / nrows
    fig.add_annotation(
        x=0.01,
        y=y,  # Top left of bottom subplot area
        xref="paper",
        yref="paper",
        text=text,
        showarrow=False,
        font=dict(size=14, color=COLOR_PALETTE[color_idx]),
        bordercolor=COLOR_PALETTE[color_idx],
        borderwidth=1,
        bgcolor="white",
        xanchor="left",
        yanchor="top",
    )


def calc_dtick(
    start_date: datetime.datetime,
    end_date: datetime.datetime,
    tdelta: datetime.timedelta,
    max_ticks: int = 20,
) -> int:
    if tdelta > datetime.timedelta(days=28):
        return "M1"
    return int(max(tdelta, (end_date - start_date) / max_ticks).total_seconds() * 1000)


def hex_to_rgba(hex_color: str, alpha: float) -> str:
    """
    Convert a hex color code to RGBA format.

    Args:
        hex_color: Hex color code (e.g., '#FF0000' or 'FF0000')
        alpha: Alpha value between 0 and 1

    Returns:
        RGBA string in format 'rgba(r, g, b, a)'
    """
    # Remove '#' if present
    hex_color = hex_color.lstrip("#")

    # Convert hex to RGB
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)

    # Return RGBA string
    return f"rgba({r}, {g}, {b}, {alpha})"

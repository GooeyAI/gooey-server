from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone as dt_timezone

from dateutil.relativedelta import relativedelta
from django.db.models import F, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone
from furl import furl

import gooey_gui as gui
from app_users.models import AppUserTransaction, TransactionReason
from bots.models.workflow import Workflow
from gooey_gui.types.credit_usage_props import (
    CreditUsagePageProps,
    CreditUsageRangeOption,
    CreditUsageSeries,
)
from widgets.plotly_theme import apply_consistent_styling, defaultPlotlyConfig
from workspaces.models import Workspace

DEFAULT_MONTHS = 6
MAX_MONTHS = 36  # how far back the range picker reaches
# categorical order from the data-viz reference palette; recipes past it fold
# into "Other" in the chart (the table still lists every recipe)
CHART_COLORS = [
    "#2a78d6",
    "#eb6834",
    "#1baf7a",
    "#eda100",
    "#e87ba4",
    "#008300",
    "#4a3aa7",
]
OTHER_COLOR = "#a3a29c"
UNATTRIBUTED_ID = "unattributed"
RANGE_PRESETS = {
    "3M": 3,
    "6M": 6,
    "12M": 12,
}


def render_credit_usage(
    workspace: Workspace,
    workspace_name: str,
    billing_href: str,
    base_href: str,
    start: str | None = None,
    end: str | None = None,
):
    this_month = _this_month()
    month_options = [
        this_month - relativedelta(months=i) for i in reversed(range(MAX_MONTHS))
    ]
    end_month = _parse_month(end) or this_month
    start_month = _parse_month(start) or (
        end_month - relativedelta(months=DEFAULT_MONTHS - 1)
    )
    if start_month > end_month:
        start_month, end_month = end_month, start_month
    # keep the range inside what the picker offers
    start_month = min(max(start_month, month_options[0]), this_month)
    end_month = min(max(end_month, month_options[0]), this_month)
    months = _month_range(start_month, end_month)

    all_series = _monthly_usage_by_workflow(workspace, month_options)
    # colours come from the whole picker window, so a recipe keeps its colour
    # whatever range is selected
    colors = {s.id: color for s, color in zip(all_series, CHART_COLORS)}
    series = _series_in_range(all_series, month_options, months)

    with gui.model_component(
        CreditUsagePageProps(
            workspace_name=workspace_name,
            months=[_fmt_month(m) for m in months],
            series=series,
            billing_href=billing_href,
            current_month=_fmt_month(this_month),
            month_options=[_fmt_month(m) for m in month_options],
            range_href=base_href,
            presets=_build_presets(base_href, this_month, months),
        )
    ):
        if series:
            _usage_chart(months, series, colors)


def _usage_chart(
    months: list[datetime],
    series: list[CreditUsageSeries],
    colors: dict[str, str],
):
    import plotly.graph_objects as go

    fig = apply_consistent_styling(go.Figure())
    other = [0] * len(months)
    for s in series:
        color = colors.get(s.id)
        if not color:
            other = [a + b for a, b in zip(other, s.credits)]
            continue
        _add_usage_bar(fig, months, s.title, s.credits, color)
    if any(other):
        _add_usage_bar(fig, months, "Other", other, OTHER_COLOR)

    fig.update_layout(
        barmode="stack",
        bargap=0.35,
        barcornerradius=4,
        height=380,
        margin=dict(l=0, r=0, t=10, b=0),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, x=0, traceorder="normal"
        ),
    )
    fig.update_xaxes(
        type="date",
        dtick="M1" if len(months) <= 12 else "M3",
        tickformat="%b<br>%Y",
        hoverformat="%B %Y",
        showgrid=False,
    )
    fig.update_yaxes(tickformat=",d", rangemode="tozero")
    gui.plotly_chart(fig, config=defaultPlotlyConfig)


def _add_usage_bar(
    fig, months: list[datetime], name: str, credits: list[int], color: str
):
    fig.add_bar(
        x=months,
        y=credits,
        name=name,
        marker=dict(color=color, line=dict(color="white", width=1)),
        hovertemplate="%{y:,} Cr",
    )


def _series_in_range(
    all_series: list[CreditUsageSeries],
    all_months: list[datetime],
    months: list[datetime],
) -> list[CreditUsageSeries]:
    lo = all_months.index(months[0])
    hi = all_months.index(months[-1]) + 1
    series = []
    for s in all_series:
        credits = s.credits[lo:hi]
        if any(credits):
            series.append(s.model_copy(update={"credits": credits}))
    series.sort(key=lambda s: sum(s.credits), reverse=True)
    return series


def _build_presets(
    base_href: str, this_month: datetime, months: list[datetime]
) -> list[CreditUsageRangeOption]:
    ranges = {
        title: this_month - relativedelta(months=n - 1)
        for title, n in RANGE_PRESETS.items()
    }
    ranges["This year"] = this_month.replace(month=1)
    return [
        CreditUsageRangeOption(
            title=title,
            href=str(
                furl(base_href).set(
                    {"start": _fmt_month(start), "end": _fmt_month(this_month)}
                )
            ),
            active=(months[0] == start and months[-1] == this_month),
        )
        for title, start in ranges.items()
    ]


def _this_month() -> datetime:
    return timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _parse_month(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        month = datetime.strptime(value, "%Y-%m")
    except ValueError:
        return None
    return month.replace(tzinfo=dt_timezone.utc)


def _month_range(start: datetime, end: datetime) -> list[datetime]:
    months = [start]
    while months[-1] < end:
        months.append(months[-1] + relativedelta(months=1))
    return months


def _fmt_month(month: datetime) -> str:
    return month.strftime("%Y-%m")


def _monthly_usage_by_workflow(
    workspace: Workspace, months: list[datetime]
) -> list[CreditUsageSeries]:
    # transactions are the billing source of truth; the linked saved run says which
    # recipe spent them
    rows = (
        AppUserTransaction.objects.filter(
            workspace=workspace,
            reason=TransactionReason.DEDUCT,
            created_at__gte=months[0],
            created_at__lt=months[-1] + relativedelta(months=1),
        )
        .annotate(
            month=TruncMonth("created_at", tzinfo=dt_timezone.utc),
            workflow=F("saved_runs__workflow"),
        )
        .values("month", "workflow")
        .annotate(credits=Sum("amount"))
        .order_by()
    )

    month_index = {_fmt_month(m): i for i, m in enumerate(months)}
    credits_by_workflow = defaultdict(lambda: [0] * len(months))
    for row in rows:
        i = month_index.get(_fmt_month(row["month"]))
        if i is None:
            continue
        credits_by_workflow[row["workflow"]][i] += -row["credits"]

    series = []
    for workflow, credits in credits_by_workflow.items():
        if not any(credits):
            continue
        if workflow is None:
            series.append(
                CreditUsageSeries(
                    id=UNATTRIBUTED_ID, title="Other charges", credits=credits
                )
            )
        else:
            workflow = Workflow(workflow)
            series.append(
                CreditUsageSeries(
                    id=workflow.short_slug,
                    title=workflow.short_title,
                    credits=credits,
                )
            )
    series.sort(key=lambda s: sum(s.credits), reverse=True)
    return series

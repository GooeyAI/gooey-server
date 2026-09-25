from __future__ import annotations

import typing

import pydantic


class CreditUsageSeries(pydantic.BaseModel):
    id: str
    title: str
    # spend in USD (credits / ADDON_CREDITS_PER_DOLLAR), one entry per month,
    # aligned with `months`
    usd: list[float]
    color: str | None = None  # the series' colour in the chart; None is "Other"


class CreditUsageRangeOption(pydantic.BaseModel):
    title: str
    href: str
    active: bool = False


class CreditUsagePageProps(pydantic.BaseModel):
    _component: str = "CreditUsagePage"

    title: str = "Usage"
    workspace_name: str
    months: list[str]  # "YYYY-MM", oldest first
    series: list[CreditUsageSeries] = []  # sorted by total spend, descending
    billing_href: str
    current_month: str  # "YYYY-MM"
    month_options: list[str] = []  # months the custom range can pick, oldest first
    range_href: str  # the page's own url, for the custom range's query params
    presets: list[CreditUsageRangeOption] = []
    chart: dict[str, typing.Any] | None = None  # plotly figure json, bars only

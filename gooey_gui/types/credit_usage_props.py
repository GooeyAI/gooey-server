from __future__ import annotations

import pydantic


class CreditUsageSeries(pydantic.BaseModel):
    id: str
    title: str
    credits: list[int]  # one entry per month, aligned with `months`


class CreditUsageRangeOption(pydantic.BaseModel):
    title: str
    href: str
    active: bool = False


class CreditUsagePageProps(pydantic.BaseModel):
    _component: str = "CreditUsagePage"

    title: str = "Usage"
    workspace_name: str
    months: list[str]  # "YYYY-MM", oldest first
    series: list[CreditUsageSeries] = []  # sorted by total credits, descending
    billing_href: str
    current_month: str  # "YYYY-MM"
    month_options: list[str] = []  # months the custom range can pick, oldest first
    range_href: str  # the page's own url, for the custom range's query params
    presets: list[CreditUsageRangeOption] = []

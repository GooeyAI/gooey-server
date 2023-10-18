import datetime

from django.conf import settings
from django.contrib import admin
from django.core.serializers import serialize
from django.db.models import QuerySet
from django.http import HttpResponse
from django.utils import dateformat


@admin.action(description="Export to CSV")
def export_to_csv(modeladmin, request, queryset):
    filename = _get_filename()
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}.csv"'
    try:
        df = queryset.to_df()
    except AttributeError as e:
        df = qs_to_df(queryset)
    df.to_csv(response, index=False)
    return response


@admin.action(description="Export to Excel")
def export_to_excel(modeladmin, request, queryset):
    filename = _get_filename()
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}.csv"'
    try:
        df = queryset.to_df()
    except AttributeError as e:
        df = qs_to_df(queryset)
    df.to_excel(response, index=False)
    return response


def qs_to_df(qs: QuerySet, limit: int = 10000):
    import pandas as pd

    return pd.DataFrame.from_records(
        [row["fields"] for row in serialize("python", qs[:limit])]
    )


def _get_filename():
    filename = f"Gooey.AI Table {dateformat.format(datetime.datetime.now(), settings.DATETIME_FORMAT)}"
    return filename

import json
import typing

from django.db import DataError
from django.db.models import F, Func, QuerySet, Count
from django.urls import reverse
from furl import furl


def json_field_nested_lookup_keys(
    qs: QuerySet,
    field: str,
    max_depth: int = 3,
    exclude_keys: typing.Iterable[str] = (),
) -> list[str]:
    nested_keys = [field]
    for _ in range(max_depth):
        next_keys = []
        for parent in nested_keys:
            try:
                next_keys.extend(
                    f"{parent}__{child}"
                    for child in (
                        qs.values(parent)
                        .annotate(keys=Func(F(parent), function="jsonb_object_keys"))
                        .order_by()
                        .distinct()
                        .values_list("keys", flat=True)
                    )
                    if not child in exclude_keys
                )
            except DataError:
                next_keys.append(parent)
        nested_keys = next_keys
    return nested_keys


def related_json_field_summary(
    manager,
    field: str,
    qs: QuerySet = None,
    query_param: str = None,
    instance_id: int = None,
    exclude_keys: typing.Iterable[str] = (),
    limit: int = None,
):
    if query_param is None:
        try:
            query_field_name = manager.field.name
        except AttributeError:
            query_field_name = manager.query_field_name
        query_param = f"{query_field_name}__id__exact"

    model = manager.model
    meta = model._meta

    if instance_id is None:
        instance_id = manager.instance.id
    if instance_id is None:
        raise model.DoesNotExist
    instance_id = str(instance_id)

    if qs is None:
        qs = manager.all()

    nested_keys = json_field_nested_lookup_keys(qs, field, exclude_keys=exclude_keys)

    results = {
        key.split(field + "__")[-1]: [
            (
                str(val),
                count,
                furl(
                    reverse(
                        f"admin:{meta.app_label}_{model.__name__.lower()}_changelist"
                    ),
                    query_params={
                        query_param: instance_id,
                        field: json.dumps([key, val]),
                    },
                ),
            )
            for val, count in (
                qs.values(key)
                .annotate(count=Count("id"))
                .order_by("-count")
                .values_list(key, "count")[:limit]
            )
            if val is not None
        ]
        for key in nested_keys
    }
    if not results:
        raise model.DoesNotExist
    return results

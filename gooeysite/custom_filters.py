import json
import typing

from django.db import DataError
from django.db.models import Count, Func, JSONField, QuerySet, TextField, Value
from django.urls import reverse
from furl import furl


def json_field_nested_lookup_keys(
    qs: QuerySet,
    field: str,
    max_depth: int = 3,
    exclude_keys: typing.Iterable[str] = (),
) -> list[tuple]:
    nested_keys = [()]
    for _ in range(max_depth):
        for i, keypath in enumerate(nested_keys):
            try:
                nested_keys.extend(
                    keypath + (key,)
                    for key in qs.values_list(
                        JSONBObjectKeys(
                            JSONBExtractPath(field, keypath) if keypath else field
                        ),
                        flat=True,
                    )
                    .order_by()
                    .distinct()
                    if key not in exclude_keys
                )
                nested_keys.pop(i)
            except DataError:
                pass
    return filter(None, nested_keys)


def related_json_field_summary(
    manager,
    field: str,
    qs: QuerySet = None,
    query_param: str = None,
    instance_id: int = None,
    exclude_keys: typing.Iterable[str] = (),
    max_keys: int = None,
) -> dict[str, typing.Any]:
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
        "__".join(keypath): [
            (
                str(val),
                count,
                furl(
                    reverse(
                        f"admin:{meta.app_label}_{model.__name__.lower()}_changelist"
                    ),
                    query_params={
                        query_param: instance_id,
                        field: json.dumps([keypath, val]),
                    },
                ),
            )
            for val, count in (
                qs.values(val=JSONBExtractPath(field, keypath))
                .annotate(count=Count("*"))
                .order_by("-count")
                .values_list("val", "count")[:max_keys]
            )
            if val is not None and val != ""
        ]
        for keypath in nested_keys
    }
    if not results:
        raise model.DoesNotExist
    return results


class JSONBExtractPath(Func):
    function = "jsonb_extract_path"
    output_field = JSONField()

    def __init__(self, from_json, path_elems, **kwargs):
        super().__init__(from_json, *map(Value, path_elems), **kwargs)


class JSONBObjectKeys(Func):
    function = "jsonb_object_keys"
    output_field = TextField()
    arity = 1

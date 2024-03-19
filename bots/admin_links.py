import re
import typing

from django.db import models
from django.template import loader
from django.urls import reverse
from django.utils.safestring import mark_safe
from furl import furl


def open_in_new_tab(url: str, *, label: str = "", add_related_url: str = None) -> str:
    label = re.sub(r"https?://", "", label)
    context = {
        "url": url,
        "label": label,
        "add_related_url": add_related_url,
    }
    html = loader.render_to_string("open_in_new_tab.html", context)
    html = mark_safe(html)
    return html


def change_obj_url(obj: models.Model, *, label: str = None) -> str:
    return open_in_new_tab(
        reverse(
            f"admin:{obj._meta.app_label}_{obj.__class__.__name__.lower()}_change",
            args=[str(obj.id)],
        ),
        label=label or str(obj),
    )


def list_related_html_url(
    manager,
    query_param: str = None,
    instance_id: int = None,
    show_add: bool = True,
    extra_label: str = None,
) -> typing.Optional[str]:
    num = manager.all().count()

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

    url = furl(
        reverse(f"admin:{meta.app_label}_{model.__name__.lower()}_changelist"),
        query_params={query_param: instance_id},
    ).url

    label = f"{num} {meta.verbose_name if num == 1 else meta.verbose_name_plural}"
    if extra_label:
        label = f"{label} ({extra_label})"

    if show_add:
        add_related_url = furl(
            reverse(f"admin:{meta.app_label}_{model.__name__.lower()}_add"),
            query_params={query_param: instance_id},
        ).url
    else:
        add_related_url = None

    html = open_in_new_tab(
        url,
        label=label,
        add_related_url=add_related_url,
    )
    return html

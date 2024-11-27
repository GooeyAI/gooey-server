import typing

import gooey_gui as gui
from django.db.models import QuerySet
from furl import furl
from starlette.datastructures import QueryParams


def remove_hostname(url: str) -> str:
    full_url = furl(url)
    short_url = furl(full_url.path)
    short_url.query = str(full_url.query)
    short_url.fragment = str(full_url.fragment)
    return str(short_url)


def remove_scheme(url: str) -> str:
    return url.removeprefix("http://").removeprefix("https://")


T = typing.TypeVar("T")


def paginate_queryset(
    *,
    qs: QuerySet[T],
    ordering: typing.Iterable[str],
    cursor: dict[str, str] | QueryParams,
    page_size: int = 21,
) -> tuple[list[T], dict[str, str] | None]:
    param_attrs = []
    for order in ordering:
        is_reversed = order.startswith("-")
        if is_reversed:
            suffix = "__lte"
        else:
            suffix = "__gte"
        # the model attribute
        attr = order.lstrip("-")
        # the queryset filter parameter, also used as query parameter
        param = attr + suffix
        # used to build the cursor later
        param_attrs.append((param, attr))
        try:
            # filter the queryset based on previous cursor
            qs = qs.filter(**{param: cursor[param]})
        except KeyError:
            pass
    # always peek one more to see if there are more pages
    page = list(qs.order_by(*ordering)[: page_size + 1])
    if len(page) > page_size:
        # build the next cursor from the first item in the next page
        cursor = {param: str(getattr(page[-1], attr)) for param, attr in param_attrs}
        # remove the last item from the results
        page = page[:-1]
    else:
        # no more pages
        cursor = None
    return page, cursor


def paginate_button(*, url, cursor: dict[str, str] | None):
    if not cursor:
        return
    f = furl(url).set(origin=None)
    f.query.params.update(cursor)
    with gui.center(), gui.link(to=str(f)):
        gui.html(
            # language=HTML
            '<button type="button" class="btn btn-theme">Load More</button>'
        )
